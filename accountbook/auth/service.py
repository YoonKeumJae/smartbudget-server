"""계정 생성·로그인 제한·JWT 인증과 본인 정보 변경을 처리합니다."""

import time

import jwt
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from accountbook.auth import security
from accountbook.auth.models import LoginAttempt, User
from accountbook.config import Settings
from accountbook.database import read_session, write_session

INVALID_LOGIN = "The username or password is incorrect."
INVALID_TOKEN = "Authentication is required or the token is invalid."
INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
CURRENT_PASSWORD_INCORRECT = "CURRENT_PASSWORD_INCORRECT"
USERNAME_CONFLICT = "USERNAME_CONFLICT"
SIGN_IN_RATE_LIMITED = "SIGN_IN_RATE_LIMITED"


class AuthError(Exception):
    """인증 처리 결과를 비밀 없는 HTTP 응답으로 전달합니다."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        retry_after: int | None = None,
    ):
        """HTTP 상태·공개 코드·메시지 및 재시도 시간을 보관합니다."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after = retry_after


def now_seconds() -> int:
    """실패 집계와 가입 시각에 사용할 UTC epoch 초를 반환합니다."""
    return int(time.time())


def register(engine: Engine, username: str, password: str, display_name: str) -> None:
    """정책을 검증하고 고유 아이디·비밀번호 해시·표시 이름을 저장합니다."""
    username = security.normalize_username(username)
    security.validate_password(password)
    display_name = security.validate_display_name(display_name)
    digest = security.hash_password(password)
    try:
        with write_session(engine) as session:
            session.add(
                User(
                    username=username,
                    password_hash=digest,
                    display_name=display_name,
                    created_at=now_seconds(),
                )
            )
    except IntegrityError as error:
        raise AuthError(
            409, USERNAME_CONFLICT, "The username is already in use."
        ) from error


def sign_in(engine: Engine, settings: Settings, username: str, password: str) -> str:
    """실패 기록을 커밋하고 현재 계정 버전의 JWT를 발급합니다."""
    username = security.normalize_username(username)
    now = now_seconds()
    error = None
    token = None
    # ponytail: 인증 쓰기를 직렬 처리, 처리량이 부족하면 해시 검증 후 상태 재확인으로 분리
    with write_session(engine) as session:
        session.execute(delete(LoginAttempt).where(LoginAttempt.expires_at <= now))
        attempt = session.get(LoginAttempt, username)
        if attempt and attempt.blocked_until and now < attempt.blocked_until:
            error = AuthError(
                429,
                SIGN_IN_RATE_LIMITED,
                "Too many sign-in attempts. Please try again later.",
                attempt.blocked_until - now,
            )
        else:
            user = session.scalar(select(User).where(User.username == username))
            digest = user.password_hash if user else security.DUMMY_PASSWORD_HASH
            valid = security.verify_password(password, digest)
            if valid and user and user.is_active:
                if attempt:
                    session.delete(attempt)
                token = security.issue_token(user.id, user.token_version, settings)
            else:
                if attempt is None:
                    attempt = LoginAttempt(
                        username=username, failures=[], expires_at=now + 300
                    )
                    session.add(attempt)
                attempt.failures = [
                    stamp for stamp in attempt.failures if stamp > now - 300
                ] + [now]
                if len(attempt.failures) >= 10:
                    attempt.blocked_until = now + 180
                    error = AuthError(
                        429,
                        SIGN_IN_RATE_LIMITED,
                        "Too many sign-in attempts. Please try again later.",
                        180,
                    )
                else:
                    error = AuthError(401, INVALID_CREDENTIALS, INVALID_LOGIN)
                attempt.expires_at = attempt.blocked_until or now + 300
    if error:
        raise error
    return token


def _claims(token: str, settings: Settings) -> dict:
    """JWT 검증 오류를 공통 인증 오류로 변환합니다."""
    try:
        return security.decode_token(token, settings)
    except (jwt.PyJWTError, ValueError, TypeError) as error:
        raise AuthError(401, AUTHENTICATION_REQUIRED, INVALID_TOKEN) from error


def _user(session: Session, claims: dict) -> User:
    """토큰의 사용자와 현재 활성·폐기 버전 상태를 대조합니다."""
    user = session.get(User, int(claims["sub"]))
    if not user or not user.is_active or user.token_version != claims["ver"]:
        raise AuthError(401, AUTHENTICATION_REQUIRED, INVALID_TOKEN)
    return user


def authenticate(engine: Engine, settings: Settings, token: str) -> User:
    """JWT와 DB 상태로 인증된 사용자를 읽기 트랜잭션에서 반환합니다."""
    claims = _claims(token, settings)
    with read_session(engine) as session:
        return _user(session, claims)


def refresh(engine: Engine, settings: Settings, token: str) -> str:
    """유효 JWT의 현재 사용자 버전을 재확인하고 새 5일 JWT를 발급합니다."""
    with write_session(engine) as session:
        user = _user(session, _claims(token, settings))
        return security.issue_token(user.id, user.token_version, settings)


def get_account(engine: Engine, settings: Settings, token: str) -> dict:
    """인증된 본인의 표시 이름과 예산만 반환합니다."""
    user = authenticate(engine, settings, token)
    return {"display_name": user.display_name, "budget_limit": user.budget_limit}


def update_account(
    engine: Engine, settings: Settings, token: str, changes: dict
) -> None:
    """본인 정보를 원자적으로 변경하고 비밀번호 변경 시 기존 JWT를 폐기합니다."""
    authenticate(engine, settings, token)
    values = dict(changes)
    if "display_name" in values:
        values["display_name"] = security.validate_display_name(values["display_name"])
    if "password" in values:
        security.validate_password(values["password"])
        values["password_hash"] = security.hash_password(values.pop("password"))
    with write_session(engine) as session:
        user = _user(session, _claims(token, settings))
        for field, value in values.items():
            setattr(user, field, value)
        if "password_hash" in values:
            user.token_version += 1
