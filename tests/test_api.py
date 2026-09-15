"""v1 인증 API의 외부 계약과 사용자 소유권을 검증합니다."""

import time
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from fastapi.testclient import TestClient

from accountbook.config import Settings
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


def test_account_lifecycle(client):
    """가입·부분 수정·갱신·비밀번호 폐기의 전체 흐름을 검증합니다."""
    result = signup(client, display_name="  홍 길동  ")
    assert result.status_code == 200
    assert result.json() == {
        "status": 200,
        "message": "The request has been accepted and processed.",
        "data": None,
    }
    assert signup(client).status_code == 409
    first = signin(client).json()["data"]["token"]
    other = signin(client).json()["data"]["token"]
    assert account(client, first).json()["data"] == {
        "display_name": "홍 길동",
        "budget_limit": None,
    }
    renewed = client.post(PREFIX + "/refresh", json={"token": first})
    assert renewed.status_code == 200
    new = renewed.json()["data"]["token"]
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
    for value in [0, 10000000, None]:
        result = client.put(
            PREFIX + "/account", json={"token": first, "budget_limit": value}
        )
        assert result.status_code == 200
        assert account(client, first).json()["data"]["budget_limit"] == value
    assert client.put(PREFIX + "/account", json={"token": first}).status_code == 200
    changed = client.put(
        PREFIX + "/account", json={"token": first, "password": "Changed12!"}
    )
    assert changed.status_code == 200 and changed.json()["data"] is None
    for token in [first, other, new]:
        assert account(client, token).status_code == 401
        assert (
            client.post(PREFIX + "/refresh", json={"token": token}).status_code == 401
        )
    assert signin(client).status_code == 401
    assert signin(client, password="Changed12!").status_code == 200


@pytest.mark.parametrize("value", [-1, 10000001, True, 1.5, "1000"])
def test_invalid_budget_is_atomic(client, value):
    """예산 오류가 있으면 표시 이름 변경도 저장되지 않습니다."""
    signup(client)
    token = signin(client).json()["data"]["token"]
    result = client.put(
        PREFIX + "/account",
        json={"token": token, "budget_limit": value, "display_name": "다른이름"},
    )
    assert result.status_code == 400
    assert account(client, token).json()["data"]["display_name"] == "홍길동"


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
    assert (
        client.put(
            PREFIX + "/account", json={"token": first, "username": "user456"}
        ).status_code
        == 400
    )
    assert client.get(PREFIX + "/account", params={"token": first}).status_code == 400
    assert client.get(PREFIX + "/account").status_code == 401
    assert client.put(PREFIX + "/account", json={}).status_code == 401
    assert client.post(PREFIX + "/refresh", json={}).status_code == 400
    assert client.post(PREFIX + "/sign-up", json={}).status_code == 400
    assert (
        client.put(
            PREFIX + "/account", json={"token": first, "display_name": None}
        ).status_code
        == 400
    )
    assert (
        client.put(
            PREFIX + "/account", json={"token": first, "password": None}
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
    import accountbook.auth as auth

    clock = [2000000000]
    monkeypatch.setattr(auth, "now_seconds", lambda: clock[0])
    signup(client)
    for _ in range(9):
        assert (
            signin(client, username="USER123", password="wrong123").status_code == 401
        )
    assert signin(client, password="wrong123").status_code == 429
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
    assert account(client, token + "broken").status_code == 401


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
    import accountbook.auth as auth

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
            first.put(
                PREFIX + "/account",
                json={
                    "token": token,
                    "password": "Changed12!",
                    "budget_limit": 1000000,
                },
            ).status_code
            == 200
        )
    with TestClient(create_app(settings)) as second:
        assert account(second, token).status_code == 401
        new = signin(second, password="Changed12!").json()["data"]["token"]
        assert account(second, new).json()["data"]["budget_limit"] == 1000000


def test_database_lock_returns_safe_503(client):
    """SQLite 잠금 대기 초과는 내부 DB 경로 없는 503으로 응답합니다."""
    from accountbook.database import write_session

    with write_session(client.app.state.engine):
        response = signup(client)
    assert response.status_code == 503
    assert response.json() == {
        "status": 503,
        "message": "The service is temporarily unavailable.",
        "data": None,
    }


def test_error_envelope_and_cors(client, caplog):
    """오류에 기밀 입력을 복사하지 않고 웹 PUT preflight를 허용합니다."""
    secret = "SensitivePassword123!"
    response = client.post(
        PREFIX + "/sign-up", json={"username": "x", "password": secret}
    )
    assert response.status_code == 400
    assert secret not in response.text and secret not in caplog.text
    response = client.options(
        PREFIX + "/account",
        headers={
            "Origin": "https://web.example.test",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://web.example.test"


def test_invalid_token_does_not_hash_new_password(client, monkeypatch):
    """인증 실패한 수정 요청은 고비용 비밀번호 해시를 실행하지 않습니다."""
    from accountbook import security

    calls = []
    monkeypatch.setattr(security, "hash_password", lambda value: calls.append(value))
    response = client.put(
        PREFIX + "/account", json={"token": "invalid", "password": "Changed12!"}
    )
    assert response.status_code == 401
    assert calls == []


def test_web_errors_and_openapi_contract(client):
    """웹 오류에도 CORS 헤더가 있으며 OpenAPI 상태표가 실제 API와 일치합니다."""
    response = client.put(
        PREFIX + "/account", json={}, headers={"Origin": "https://web.example.test"}
    )
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "https://web.example.test"
    assert "Retry-After" in response.headers["access-control-expose-headers"]
    schema = client.get("/openapi.json").json()
    route = schema["paths"][PREFIX + "/sign-up"]["post"]
    assert "400" in route["responses"] and "409" in route["responses"]
    assert "422" not in route["responses"]
    assert route["responses"]["200"]["content"]["application/json"]["schema"]
