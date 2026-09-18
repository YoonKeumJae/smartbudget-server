"""v1 인증 API의 외부 계약과 사용자 소유권을 검증합니다."""

import time
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from accountbook.auth.models import LoginAttempt, User
from accountbook.config import Settings
from accountbook.database import read_session
from accountbook.main import create_app

PREFIX = "/api/v1/auth"


@pytest.fixture
def client(tmp_path):
    """독립 파일 DB와 비밀 없는 테스트 설정을 제공합니다."""
    settings = Settings(
        _env_file=None,
        jwt_secret="x" * 43,
        database_path=tmp_path / "test.sqlite3",
        web_origins=["https://web.example.test"],
    )
    with TestClient(
        create_app(settings), base_url="https://api.example.test"
    ) as result:
        yield result


def signup(client, username="User123", password="Abcdef12", display_name="홍길동"):
    """명시된 계정을 등록해 테스트의 실제 인증 흐름을 준비합니다."""
    return client.post(
        PREFIX + "/sign-up",
        json=dict(username=username, password=password, display_name=display_name),
    )


def signin(client, username="user123", password="Abcdef12"):
    """실제 로그인 응답에서 JWT를 추출합니다."""
    return client.post(
        PREFIX + "/sign-in", json=dict(username=username, password=password)
    )


def account(client, token):
    """GET 계정 조회에 Bearer 헤더만 사용합니다."""
    return client.get(PREFIX + "/account", headers={"Authorization": "Bearer " + token})


def patch_account(client, token, payload):
    """PATCH 계정 수정에 Bearer 헤더와 변경 JSON만 전달합니다."""
    return client.patch(
        PREFIX + "/account",
        headers={"Authorization": "Bearer " + token},
        json=payload,
    )


def delete_account(client, token):
    """DELETE 계정 삭제에 Bearer 헤더만 전달합니다."""
    return client.delete(
        PREFIX + "/account", headers={"Authorization": "Bearer " + token}
    )


def test_delete_account_removes_user_and_invalidates_token(client):
    """본인 삭제 후 계정·로그인 제한·기존 JWT를 다시 사용할 수 없습니다."""
    signup(client)
    token = signin(client).json()["data"]["token"]
    assert signin(client, password="Wrong123").status_code == 401
    with read_session(client.app.state.engine) as session:
        assert session.get(LoginAttempt, "user123") is not None

    response = delete_account(client, token)

    assert response.status_code == 200
    assert response.json()["data"] is None
    assert account(client, token).status_code == 401
    with read_session(client.app.state.engine) as session:
        assert session.scalar(select(User).where(User.username == "user123")) is None
        assert session.get(LoginAttempt, "user123") is None
    assert signin(client).status_code == 401
    assert signup(client).status_code == 200
    new_token = signin(client).json()["data"]["token"]
    assert account(client, token).status_code == 401
    assert account(client, new_token).status_code == 200


def test_delete_account_keeps_other_user(client):
    """본인 삭제가 다른 사용자와 그 로그인 제한 상태에 영향을 주지 않습니다."""
    signup(client)
    signup(client, username="User456", display_name="다른사용자")
    first_token = signin(client).json()["data"]["token"]
    second_token = signin(client, username="user456").json()["data"]["token"]
    assert signin(client, password="Wrong123").status_code == 401
    assert signin(client, username="user456", password="Wrong123").status_code == 401

    assert delete_account(client, first_token).status_code == 200

    assert account(client, second_token).json()["data"] == {
        "display_name": "다른사용자"
    }
    with read_session(client.app.state.engine) as session:
        assert session.scalar(select(User).where(User.username == "user456"))
        assert session.get(LoginAttempt, "user456") is not None


def test_delete_account_authentication_and_input_contract(client):
    """DELETE는 Bearer JWT만 받고 query·본문은 요청 오류로 거부합니다."""
    signup(client)
    token = signin(client).json()["data"]["token"]
    for response in [
        client.delete(PREFIX + "/account"),
        client.delete(PREFIX + "/account", headers={"Authorization": "Bearer invalid"}),
    ]:
        assert response.status_code == 401
        assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
        assert response.headers["www-authenticate"] == "Bearer"
    for response in [
        client.delete(
            PREFIX + "/account",
            params={"token": token},
            headers={"Authorization": "Bearer " + token},
        ),
        client.request(
            "DELETE",
            PREFIX + "/account",
            headers={"Authorization": "Bearer " + token},
            json={},
        ),
    ]:
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"


def test_account_lifecycle(client):
    """가입·부분 수정·갱신·비밀번호 폐기의 전체 흐름을 검증합니다."""
    result = signup(client, display_name="  홍 길동  ")
    assert result.status_code == 200
    assert result.json() == {
        "status": 200,
        "code": "SUCCESS",
        "message": "The request has been accepted and processed.",
        "data": None,
    }
    conflict = signup(client)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "USERNAME_CONFLICT"
    sign_in_data = signin(client).json()["data"]
    assert set(sign_in_data) == {"token", "expires_at", "token_type"}
    first = sign_in_data["token"]
    other = signin(client).json()["data"]["token"]
    assert account(client, first).json()["data"] == {"display_name": "홍 길동"}
    renewed = client.post(PREFIX + "/refresh", json={"token": first})
    assert renewed.status_code == 200
    refresh_data = renewed.json()["data"]
    assert set(refresh_data) == {"token", "expires_at", "token_type"}
    new = refresh_data["token"]
    assert first != new
    claims = jwt.decode(
        new,
        client.app.state.settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience="accountbook-api",
        issuer="accountbook",
    )
    assert claims["exp"] - claims["iat"] == 432000
    assert account(client, first).status_code == 200
    renamed = patch_account(client, first, {"display_name": "새 이름"})
    assert renamed.status_code == 200
    assert renamed.json()["data"] == {"display_name": "새 이름"}
    assert account(client, first).status_code == 200
    changed = patch_account(
        client,
        first,
        {"current_password": "Abcdef12", "password": "Changed12!"},
    )
    assert changed.status_code == 200
    assert changed.json()["data"] == {"display_name": "새 이름"}
    for token in [first, other, new]:
        assert account(client, token).status_code == 401
        assert (
            client.post(PREFIX + "/refresh", json={"token": token}).status_code == 401
        )
    invalid_credentials = signin(client)
    assert invalid_credentials.status_code == 401
    assert invalid_credentials.json()["code"] == "INVALID_CREDENTIALS"
    assert signin(client, password="Changed12!").status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"display_name": None},
        {"password": None, "current_password": "Abcdef12"},
        {"password": "Changed12!", "current_password": None},
        {"password": "Changed12!"},
        {"current_password": "Abcdef12"},
        {"budget_limit": 1000},
    ],
)
def test_invalid_account_update_contract(client, payload):
    """빈 값·null·불완전 비밀번호 쌍·폐기 필드를 오류 코드 400으로 거부합니다."""
    signup(client)
    token = signin(client).json()["data"]["token"]
    result = patch_account(client, token, payload)
    assert result.status_code == 400
    assert result.json()["code"] == "INVALID_REQUEST"


def test_wrong_current_password_keeps_all_account_values(client):
    """현재 비밀번호가 틀리면 표시 이름과 비밀번호를 함께 유지합니다."""
    signup(client)
    token = signin(client).json()["data"]["token"]
    result = patch_account(
        client,
        token,
        {
            "current_password": "wrong123",
            "password": "Changed12!",
            "display_name": "다른이름",
        },
    )
    assert result.status_code == 401
    assert result.json()["code"] == "CURRENT_PASSWORD_INCORRECT"
    assert account(client, token).json()["data"] == {"display_name": "홍길동"}
    assert signin(client).status_code == 200
    assert signin(client, password="Changed12!").status_code == 401


@pytest.mark.parametrize(
    "name", ["가", "가" * 11, "홍!", "홍😀", "   ", "\t홍길동", "홍\n길동"]
)
def test_invalid_display_name(client, name):
    """표시 이름의 길이·문자·제어문자 규칙을 지킵니다."""
    assert signup(client, display_name=name).status_code == 400


def test_user_isolation_and_input_contract(client):
    """다른 사용자 선택 입력과 토큰의 잘못된 전달 위치를 거부합니다."""
    signup(client)
    signup(client, username="User456", display_name="다른사용자")
    first = signin(client).json()["data"]["token"]
    second = signin(client, username="user456").json()["data"]["token"]
    assert account(client, second).json()["data"]["display_name"] == "다른사용자"
    assert patch_account(client, first, {"username": "user456"}).status_code == 400
    assert client.get(PREFIX + "/account", params={"token": first}).status_code == 400
    assert client.get(PREFIX + "/account").status_code == 401
    assert (
        client.patch(PREFIX + "/account", json={"display_name": "새 이름"}).status_code
        == 401
    )
    assert client.post(PREFIX + "/refresh", json={}).status_code == 400
    assert client.post(PREFIX + "/sign-up", json={}).status_code == 400
    assert client.patch(PREFIX + "/account", json={"token": first}).status_code == 400
    assert (
        client.patch(
            PREFIX + "/account",
            headers={"Authorization": "Bearer " + first},
            json={"token": first, "display_name": "새 이름"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            PREFIX + "/refresh",
            json={"token": first},
            headers={"Authorization": "Bearer " + first},
        ).status_code
        == 400
    )


def test_login_block_does_not_extend(client, monkeypatch):
    """대소문자 공유 실패 집계와 정확한 차단 종료 시각을 검사합니다."""
    from accountbook.auth import service as auth

    clock = [2000000000]
    monkeypatch.setattr(auth, "now_seconds", lambda: clock[0])
    signup(client)
    for _ in range(9):
        assert (
            signin(client, username="USER123", password="wrong123").status_code == 401
        )
    limited = signin(client, password="wrong123")
    assert limited.status_code == 429
    assert limited.json()["code"] == "SIGN_IN_RATE_LIMITED"
    clock[0] += 179
    blocked = signin(client)
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "1"
    clock[0] += 1
    assert signin(client).status_code == 200


def test_expired_and_invalid_claims(client):
    """만료·변조·잘못된 사용자와 필수 항목 누락 JWT를 거부합니다."""
    signup(client)
    token = signin(client).json()["data"]["token"]
    settings = client.app.state.settings
    key = settings.jwt_secret.get_secret_value()
    claims = jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    for changes in [
        {"exp": int(time.time())},
        {"sub": "999999"},
        {"ver": True},
        {"iat": int(time.time()) + 600},
        {"aud": "other"},
    ]:
        wrong = jwt.encode({**claims, **changes}, key, algorithm="HS256")
        assert (
            client.post(PREFIX + "/refresh", json={"token": wrong}).status_code == 401
        )
    for field in claims:
        missing = dict(claims)
        missing.pop(field)
        wrong = jwt.encode(missing, key, algorithm="HS256")
        assert account(client, wrong).status_code == 401
    invalid_token = account(client, token + "broken")
    assert invalid_token.status_code == 401
    assert invalid_token.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_concurrent_failures(client):
    """독립 연결의 동시 실패가 차단 집계를 잃지 않습니다."""
    signup(client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: signin(client, password="Wrong123").status_code, range(10)
            )
        )
    assert sorted(results) == [401] * 9 + [429]
    assert signin(client).status_code == 429


def test_failure_window_and_unknown_user(client, monkeypatch):
    """5분 경계의 실패 제거와 미가입 아이디에도 같은 차단을 적용합니다."""
    from accountbook.auth import service as auth

    clock = [2000000000]
    monkeypatch.setattr(auth, "now_seconds", lambda: clock[0])
    signup(client)
    for _ in range(9):
        assert signin(client, password="wrong123").status_code == 401
    clock[0] += 300
    assert signin(client, password="wrong123").status_code == 401
    assert signin(client).status_code == 200
    for _ in range(9):
        response = signin(client, username="Missing123", password="Wrong123")
        assert response.status_code == 401
        assert response.json()["message"] == "The username or password is incorrect."
    assert signin(client, username="MISSING123", password="Wrong123").status_code == 429


def test_restart_keeps_user_and_revocation(tmp_path):
    """파일 DB 재시작 후에도 정보와 기존 JWT 폐기 상태를 유지합니다."""
    settings = Settings(
        _env_file=None,
        jwt_secret="x" * 43,
        database_path=tmp_path / "persistent.sqlite3",
    )
    with TestClient(create_app(settings)) as first:
        signup(first)
        token = signin(first).json()["data"]["token"]
        assert (
            patch_account(
                first,
                token,
                {"current_password": "Abcdef12", "password": "Changed12!"},
            ).status_code
            == 200
        )
    with TestClient(create_app(settings)) as second:
        assert account(second, token).status_code == 401
        new = signin(second, password="Changed12!").json()["data"]["token"]
        assert account(second, new).json()["data"] == {"display_name": "홍길동"}


def test_database_lock_returns_safe_503(client):
    """SQLite 잠금 대기 초과는 내부 DB 경로 없는 503으로 응답합니다."""
    from accountbook.database import write_session

    with write_session(client.app.state.engine):
        response = signup(client)
    assert response.status_code == 503
    assert response.json() == {
        "status": 503,
        "code": "SERVICE_UNAVAILABLE",
        "message": "The service is temporarily unavailable.",
        "data": None,
    }


def test_error_envelope_and_cors(client, caplog):
    """오류에 기밀 입력을 복사하지 않고 웹 PATCH preflight를 허용합니다."""
    secret = "SensitivePassword123!"
    response = client.post(
        PREFIX + "/sign-up", json={"username": "x", "password": secret}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
    assert secret not in response.text and secret not in caplog.text
    response = client.options(
        PREFIX + "/account",
        headers={
            "Origin": "https://web.example.test",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://web.example.test"


def test_invalid_token_does_not_hash_new_password(client, monkeypatch):
    """인증 실패한 수정 요청은 고비용 비밀번호 해시를 실행하지 않습니다."""
    from accountbook.auth import security

    calls = []
    monkeypatch.setattr(security, "hash_password", lambda value: calls.append(value))
    response = client.patch(
        PREFIX + "/account",
        headers={"Authorization": "Bearer invalid"},
        json={"current_password": "Abcdef12", "password": "Changed12!"},
    )
    assert response.status_code == 401
    assert calls == []


def test_web_errors_and_openapi_contract(client):
    """웹 오류에도 CORS 헤더가 있으며 OpenAPI 상태표가 실제 API와 일치합니다."""
    response = client.patch(
        PREFIX + "/account",
        json={"display_name": "새 이름"},
        headers={"Origin": "https://web.example.test"},
    )
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "https://web.example.test"
    assert "Retry-After" in response.headers["access-control-expose-headers"]
    schema = client.get("/openapi.json").json()
    route = schema["paths"][PREFIX + "/sign-up"]["post"]
    assert "400" in route["responses"] and "409" in route["responses"]
    assert "422" not in route["responses"]
    assert route["responses"]["200"]["content"]["application/json"]["schema"]


def test_openapi_token_expiration_contract(client):
    """생성 OpenAPI가 토큰 만료 시각의 형식과 한국 시간 패턴을 명시합니다."""
    schema = client.get("/openapi.json").json()
    expires_at = schema["components"]["schemas"]["TokenData"]["properties"][
        "expires_at"
    ]
    assert expires_at["format"] == "date-time"
    assert expires_at["pattern"] == (
        r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):"
        r"[0-5][0-9]:[0-5][0-9]\+09:00(?![\s\S])"
    )
    assert expires_at["description"] == (
        "발급한 JWT가 만료되는 한국 시간입니다. JWT의 exp와 같은 시점입니다."
    )
    assert expires_at["example"] == "2026-09-21T14:30:00+09:00"


def test_openapi_account_update_fields_match_target_contract(client):
    """PATCH 계정 수정 필드가 null 없이 목표 제약을 생성 OpenAPI에 공개합니다."""
    schema = client.get("/openapi.json").json()
    request_schema = schema["paths"][PREFIX + "/account"]["patch"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    assert request_schema == {"$ref": "#/components/schemas/AccountUpdate"}
    update = schema["components"]["schemas"]["AccountUpdate"]
    properties = {
        name: {key: value for key, value in field.items() if key != "title"}
        for name, field in update["properties"].items()
    }
    assert properties == {
        "password": {
            "type": "string",
            "minLength": 8,
            "maxLength": 20,
            "format": "password",
            "writeOnly": True,
            "pattern": (
                r"^(?:(?=.*[A-Za-z])(?=.*[0-9])|"
                r"(?=.*[A-Za-z])(?=.*[!@#$%^&*_=+?\-])|"
                r"(?=.*[0-9])(?=.*[!@#$%^&*_=+?\-]))"
                r"[A-Za-z0-9!@#$%^&*_=+?\-]{8,20}(?![\s\S])"
            ),
            "description": (
                "비밀번호: 8–20자, `A–Z`, `a–z`, `0–9`, `!@#$%^&*_-+=?`만 "
                "허용합니다. 영문·숫자·특수문자 세 종류 중 두 종류 이상이 "
                "필요합니다. 대소문자를 구분하며 공백·한글·그 외 문자를 "
                "거부합니다. 가입·비밀번호 변경에 이 정책을 적용하며, 로그인은 "
                "입력한 비밀번호를 해시와 비교합니다."
            ),
        },
        "display_name": {
            "type": "string",
            "pattern": (
                r"^ *[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ]"
                r"[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ ]{0,8}"
                r"[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ] *(?![\s\S])"
            ),
            "description": (
                "표시 이름: 일반 공백을 앞뒤에서 제거한 후 2–10자입니다. 한글 "
                "음절·자모, ASCII 영문·숫자·일반 공백만 허용합니다. 중간 공백을 "
                "유지하고 글자 수에 포함합니다. 공백만 있는 이름·탭·줄바꿈·"
                "제어문자·다른 특수문자를 거부합니다. 중복은 허용합니다. 원본 "
                "입력은 앞뒤 공백을 포함하여 최대 256자이며, 공백 제거 후 2–10자 "
                "제한은 pattern으로 검사합니다."
            ),
            "maxLength": 256,
        },
        "current_password": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128,
            "format": "password",
            "writeOnly": True,
            "description": (
                "password를 바꿀 때 확인할 현재 비밀번호입니다. password와 함께 "
                "전달해야 합니다."
            ),
        },
    }
    assert update["minProperties"] == 1
    assert update["dependentRequired"] == {
        "password": ["current_password"],
        "current_password": ["password"],
    }


def test_router_uses_each_apps_database_and_settings(tmp_path):
    """공유 인증 라우터가 서로 다른 앱의 DB·JWT 서명키를 혼용하지 않습니다."""
    first_settings = Settings(
        _env_file=None, jwt_secret="a" * 43, database_path=tmp_path / "first.sqlite3"
    )
    second_settings = Settings(
        _env_file=None, jwt_secret="b" * 43, database_path=tmp_path / "second.sqlite3"
    )
    with TestClient(create_app(first_settings)) as first:
        with TestClient(create_app(second_settings)) as second:
            assert signup(first, display_name="첫 사용자").status_code == 200
            assert signup(second, display_name="둘 사용자").status_code == 200
            first_token = signin(first).json()["data"]["token"]
            second_token = signin(second).json()["data"]["token"]
            for client, token, name in [
                (first, first_token, "첫 사용자"),
                (second, second_token, "둘 사용자"),
            ]:
                response = client.get(
                    PREFIX + "/account", headers={"Authorization": "Bearer " + token}
                )
                assert response.status_code == 200
                assert response.json()["data"]["display_name"] == name
            assert (
                first.get(
                    PREFIX + "/account",
                    headers={"Authorization": "Bearer " + second_token},
                ).status_code
                == 401
            )
            assert (
                second.get(
                    PREFIX + "/account",
                    headers={"Authorization": "Bearer " + first_token},
                ).status_code
                == 401
            )
