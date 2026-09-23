"""입력 정책·비밀번호 해시·JWT 검증을 인증 서비스에 제공합니다."""

import re
import time
from datetime import datetime
from threading import BoundedSemaphore
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from smartbudget_server.config import Settings

_PASSWORD_HASH = PasswordHash.recommended()
_HASH_SLOT = BoundedSemaphore(1)
_REQUIRED_CLAIMS = ["sub", "ver", "jti", "iat", "exp", "iss", "aud"]
KOREA_TIMEZONE = ZoneInfo("Asia/Seoul")


def now_seconds() -> int:
    """JWT 발급 시각으로 사용할 현재 UTC epoch 초를 반환합니다."""
    return int(time.time())


def normalize_username(value: str) -> str:
    """가입·로그인·실패 집계가 같은 ASCII 아이디 규칙을 사용하게 합니다."""
    if re.fullmatch(r"[A-Za-z0-9]{4,12}", value) is None:
        raise ValueError("Invalid username")
    return value.lower()


def validate_password(value: str) -> str:
    """가입·변경 비밀번호의 허용 문자와 두 종류 조합을 원문으로 검사합니다."""
    if re.fullmatch(r"[A-Za-z0-9!@#$%^&*_=+?\-]{8,20}", value) is None:
        raise ValueError("Invalid password")
    kinds = sum(
        bool(re.search(pattern, value))
        for pattern in (r"[A-Za-z]", r"[0-9]", r"[!@#$%^&*_=+?\-]")
    )
    if kinds < 2:
        raise ValueError("Invalid password")
    return value


def validate_display_name(value: str) -> str:
    """표시 이름의 제어문자를 거부하고 앞뒤 일반 공백만 정리합니다."""
    if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value):
        raise ValueError("Invalid display name")
    value = value.strip(" ")
    if re.fullmatch(r"[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ ]{2,10}", value) is None:
        raise ValueError("Invalid display name")
    return value


def hash_password(value: str) -> str:
    """동시 해시 메모리를 제한하며 사용자 비밀번호를 Argon2id로 저장합니다."""
    with _HASH_SLOT:
        return _PASSWORD_HASH.hash(value)


def verify_password(value: str, digest: str) -> bool:
    """실제·더미 해시 모두 같은 제한 아래 원문 비밀번호를 비교합니다."""
    with _HASH_SLOT:
        try:
            return _PASSWORD_HASH.verify(value, digest)
        except UnknownHashError:
            return False


DUMMY_PASSWORD_HASH = hash_password("DummyPassword123!")


def issue_token(user_id: int, version: int, settings: Settings) -> str:
    """검증된 사용자 ID·버전으로 설정된 수명의 HS256 JWT를 발급합니다."""
    issued_at = now_seconds()
    return jwt.encode(
        {
            "sub": str(user_id),
            "ver": version,
            "jti": str(uuid4()),
            "iat": issued_at,
            "exp": issued_at + settings.token_seconds,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_token(value: str, settings: Settings) -> dict:
    """PyJWT 시간·서명 검증과 필수 claims 자료형을 검사해 인증에 전달합니다."""
    try:
        claims = jwt.decode(
            value,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": _REQUIRED_CLAIMS},
        )
    except TypeError, ValueError, OverflowError:
        raise jwt.InvalidTokenError("Invalid token claims") from None
    invalid = (
        not isinstance(claims["sub"], str)
        or re.fullmatch(r"[1-9][0-9]*", claims["sub"]) is None
        or len(claims["sub"]) > 19
        or int(claims["sub"]) > 9223372036854775807
        or type(claims["ver"]) is not int
        or claims["ver"] < 0
        or type(claims["iat"]) is not int
        or type(claims["exp"]) is not int
        or claims["exp"] <= claims["iat"]
        or not isinstance(claims["iss"], str)
        or not isinstance(claims["aud"], str)
        or not isinstance(claims["jti"], str)
    )
    if invalid:
        raise jwt.InvalidTokenError("Invalid token claims")
    try:
        UUID(claims["jti"])
    except ValueError:
        raise jwt.InvalidTokenError("Invalid token claims") from None
    return claims


def token_data(token: str, settings: Settings) -> dict[str, str]:
    """검증된 JWT와 exp를 클라이언트용 Bearer 토큰 데이터로 변환합니다."""
    expires_at = datetime.fromtimestamp(
        decode_token(token, settings)["exp"], KOREA_TIMEZONE
    ).isoformat(timespec="seconds")
    return {"token": token, "expires_at": expires_at, "token_type": "Bearer"}
