"""사용자 입력 정책과 실제 Argon2·JWT 검증을 확인합니다."""

import time
from datetime import datetime, timedelta

import jwt
import pytest

from smartbudget_server.auth.security import (
    decode_token,
    hash_password,
    issue_token,
    normalize_username,
    token_data,
    validate_display_name,
    validate_password,
    verify_password,
)
from smartbudget_server.config import Settings


def test_input_policy():
    """아이디 정규화·허용 문자와 비밀번호 두 종류 조합을 검사합니다."""
    assert normalize_username("User123") == "user123"
    for value in ("abc", "a" * 13, "한글123", "user_123"):
        with pytest.raises(ValueError):
            normalize_username(value)
    for value in ("Abcdef12", "1234567!", "Abcdefg!", "A1" + "x" * 18):
        assert validate_password(value) == value
    for character in "!@#$%^&*_-+=?":
        assert validate_password("Abcdefg" + character)
    for value in (
        "Abcdefgh",
        "12345678",
        "!" * 8,
        "A123456",
        "A1" + "x" * 19,
        "Abcdef1 ",
        "Abcdef1한",
    ):
        with pytest.raises(ValueError):
            validate_password(value)
    assert validate_display_name("  홍 길동  ") == "홍 길동"
    assert validate_display_name("ㄱㅏ") == "ㄱㅏ"
    for value in ("홍", "가" * 11, "  ", "홍길동\n", "홍\t길", "홍길동!", "홍길😀"):
        with pytest.raises(ValueError):
            validate_display_name(value)


def test_password_hash():
    """해시 소금이 달라지고 비밀번호 대소문자를 구분합니다."""
    digest = hash_password("Abcdef12")
    assert digest.startswith("$argon2id$")
    assert digest != hash_password("Abcdef12")
    assert verify_password("Abcdef12", digest)
    assert not verify_password("abcdef12", digest)


def test_jwt_contract():
    """실제 UTC 시간으로 발급하고 위조·만료·claims 오류를 거부합니다."""
    settings = Settings(_env_file=None, jwt_secret="x" * 43)
    token = issue_token(1, 0, settings)
    claims = decode_token(token, settings)
    assert claims["sub"] == "1"
    assert claims["exp"] - claims["iat"] == 432000
    assert token != issue_token(1, 0, settings)
    for name in claims:
        bad = claims.copy()
        del bad[name]
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(
                jwt.encode(
                    bad, settings.jwt_secret.get_secret_value(), algorithm="HS256"
                ),
                settings,
            )
    changes = [
        {"exp": int(time.time())},
        {"iat": int(time.time()) + 60},
        {"iss": "other"},
        {"aud": "other"},
        {"sub": "0"},
        {"ver": True},
        {"iat": "123"},
        {"iat": []},
        {"exp": []},
        {"ver": -1},
        {"ver": "0"},
        {"aud": [settings.jwt_audience]},
        {"exp": 1.5},
        {"jti": "invalid"},
    ]
    for change in changes:
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(
                jwt.encode(
                    claims | change,
                    settings.jwt_secret.get_secret_value(),
                    algorithm="HS256",
                ),
                settings,
            )
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(jwt.encode(claims, "z" * 43, algorithm="HS256"), settings)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(
            jwt.encode(claims, "z" * 64, algorithm="HS384"),
            settings,
        )


def test_token_data_matches_exp():
    """응답 만료 시각이 JWT exp와 같고 한국 시간 오프셋을 사용합니다."""
    settings = Settings(_env_file=None, jwt_secret="x" * 43)
    token = issue_token(1, 0, settings)
    claims = decode_token(token, settings)
    data = token_data(token, settings)
    assert data["token"] == token
    assert data["token_type"] == "Bearer"
    expires_at = datetime.fromisoformat(data["expires_at"])
    assert expires_at.utcoffset() == timedelta(hours=9)
    assert int(expires_at.timestamp()) == claims["exp"]


def test_corrupt_hash_is_authentication_failure():
    """손상된 DB 비밀번호 해시를 내부 오류 대신 로그인 실패로 처리합니다."""
    assert not verify_password("Abcdef12", "corrupt")
    assert not verify_password("Abcdef12", "$argon2id$v=19$m=65536,t=3,p=4")


def test_token_user_id_fits_sqlite_integer():
    """서명된 토큰이어도 SQLite 정수 범위를 넘는 사용자 ID를 거부합니다."""
    settings = Settings(_env_file=None, jwt_secret="x" * 43)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(issue_token(9223372036854775808, 0, settings), settings)
