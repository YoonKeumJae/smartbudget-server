"""로그인 제한·JWT 검증·전송 오류와 DB 장애 응답을 검증합니다."""

import time
from concurrent.futures import ThreadPoolExecutor

import jwt

from tests.auth.helpers import PREFIX, account, signin, signup


def test_login_block_does_not_extend(client, monkeypatch):
    """대소문자 공유 실패 집계와 정확한 차단 종료 시각을 검사합니다."""
    from smartbudget_server.auth import service as auth

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
    from smartbudget_server.auth import service as auth

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


def test_database_lock_returns_safe_503(client):
    """SQLite 잠금 대기 초과는 내부 DB 경로 없는 503으로 응답합니다."""
    from smartbudget_server.database import write_session

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


def test_signin_keeps_general_password_comparison(client):
    """스키마 문서화가 로그인 원문 비교와 길이 오류 응답을 바꾸지 않습니다."""
    signup(client)
    for password in ("", "a", "한 글", "a" * 128):
        response = signin(client, password=password)
        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_CREDENTIALS"
    response = signin(client, password="a" * 129)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
