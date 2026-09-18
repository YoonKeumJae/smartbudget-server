"""인증 라우트와 이 기능의 토큰 전달·인증 오류 규칙을 등록합니다."""

from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from accountbook.auth import security, service
from accountbook.auth.schemas import (
    AccountData,
    AccountUpdate,
    Credentials,
    RefreshRequest,
    Registration,
    TokenData,
)
from accountbook.http import ERROR_RESPONSES, INVALID_REQUEST, Envelope, respond

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False, scheme_name="BearerAuth")


def bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    """파싱된 Authorization 헤더를 공통 Bearer 인증 오류로 변환합니다."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise service.AuthError(
            401, service.AUTHENTICATION_REQUIRED, service.INVALID_TOKEN
        )
    return credentials.credentials


@router.post(
    "/sign-up",
    response_model=Envelope[None],
    responses={code: ERROR_RESPONSES[code] for code in [400, 409, 503]},
)
def sign_up(payload: Registration, request: Request):
    """필수 이름·아이디·비밀번호로 계정을 생성합니다."""
    service.register(
        request.app.state.engine,
        payload.username,
        payload.password.get_secret_value(),
        payload.display_name,
    )
    return respond(200)


@router.post(
    "/sign-in",
    response_model=Envelope[TokenData],
    responses={code: ERROR_RESPONSES[code] for code in [400, 401, 429, 503]},
)
def sign_in(payload: Credentials, request: Request):
    """로그인 제한을 적용하고 JWT와 실제 만료 정보를 반환합니다."""
    token = service.sign_in(
        request.app.state.engine,
        request.app.state.settings,
        payload.username,
        payload.password.get_secret_value(),
    )
    return respond(200, security.token_data(token, request.app.state.settings))


@router.post(
    "/refresh",
    response_model=Envelope[TokenData],
    responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
)
def refresh(payload: RefreshRequest, request: Request):
    """유효한 JWT로 새 토큰을 발급하고 실제 만료 정보를 반환합니다."""
    token = service.refresh(
        request.app.state.engine, request.app.state.settings, payload.token
    )
    return respond(200, security.token_data(token, request.app.state.settings))


@router.get(
    "/account",
    response_model=Envelope[AccountData],
    responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
)
def get_account(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """Authorization Bearer로 인증된 본인의 정보만 반환합니다."""
    return respond(
        200,
        service.get_account(
            request.app.state.engine,
            request.app.state.settings,
            bearer_token(credentials),
        ),
    )


@router.patch(
    "/account",
    response_model=Envelope[AccountData],
    responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
)
def update_account(
    payload: AccountUpdate,
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """Bearer JWT로 인증해 제공된 본인 정보만 원자적으로 수정합니다."""
    changes = payload.model_dump(exclude_unset=True)
    for field in ("password", "current_password"):
        if field in changes:
            changes[field] = changes[field].get_secret_value()
    result = service.update_account(
        request.app.state.engine,
        request.app.state.settings,
        bearer_token(credentials),
        changes,
    )
    return respond(200, result)


@router.delete(
    "/account",
    response_model=Envelope[None],
    responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
)
def delete_account(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """Bearer JWT로 인증된 본인 계정과 현재 로그인 제한 상태를 삭제합니다."""
    service.delete_account(
        request.app.state.engine,
        request.app.state.settings,
        bearer_token(credentials),
    )
    return respond(200)


def configure_auth(app: FastAPI) -> None:
    """앱에 인증 전송 규칙·인증 오류 처리와 라우터를 함께 등록합니다."""

    @app.middleware("http")
    async def enforce_transport(request: Request, call_next):
        """갱신 토큰 혼용과 비JSON 쓰기 및 조회·삭제 본문을 거부합니다."""
        if request.url.path.startswith("/api/v1/auth/"):
            if request.query_params:
                return respond(400, code="INVALID_REQUEST", message=INVALID_REQUEST)
            if request.method in {"GET", "DELETE"} and await request.body():
                return respond(400, code="INVALID_REQUEST", message=INVALID_REQUEST)
            if request.method in {"POST", "PATCH"}:
                if (
                    request.headers.get("content-type", "")
                    .split(";")[0]
                    .strip()
                    .lower()
                    != "application/json"
                ):
                    return respond(400, code="INVALID_REQUEST", message=INVALID_REQUEST)
                if (
                    request.url.path.endswith("/refresh")
                    and "authorization" in request.headers
                ):
                    return respond(400, code="INVALID_REQUEST", message=INVALID_REQUEST)
        return await call_next(request)

    @app.exception_handler(service.AuthError)
    async def auth_error(request: Request, error: service.AuthError):
        """인증 실패와 차단 상태를 HTTP 계약의 헤더와 함께 반환합니다."""
        headers = {}
        if error.status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        if error.retry_after is not None:
            headers["Retry-After"] = str(error.retry_after)
        return respond(
            error.status_code,
            code=error.code,
            message=error.message,
            headers=headers,
        )

    app.include_router(router)
