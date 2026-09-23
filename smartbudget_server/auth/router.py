"""인증 라우트와 이 기능의 토큰 전달·인증 오류 규칙을 등록합니다."""

from typing import Annotated

from fastapi import APIRouter, FastAPI, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from smartbudget_server.auth import security, service
from smartbudget_server.auth.schemas import (
    AccountData,
    AccountUpdate,
    AuthenticationRequiredEnvelope,
    Credentials,
    CurrentPasswordIncorrectEnvelope,
    InvalidCredentialsEnvelope,
    InvalidRequestEnvelope,
    RefreshRequest,
    Registration,
    ServiceUnavailableEnvelope,
    SignInRateLimitedEnvelope,
    SuccessEnvelope,
    TokenData,
    UsernameConflictEnvelope,
)
from smartbudget_server.http import INVALID_REQUEST, documented_response, respond

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    description="Authorization: Bearer <JWT> 헤더로 인증합니다.",
)

INVALID_REQUEST_RESPONSE = documented_response(
    InvalidRequestEnvelope, "The request parameters or format are invalid."
)
AUTHENTICATION_REQUIRED_RESPONSE = documented_response(
    AuthenticationRequiredEnvelope,
    "Authentication is required or the token is invalid.",
    authentication=True,
)
SERVICE_UNAVAILABLE_RESPONSE = documented_response(
    ServiceUnavailableEnvelope, "The service is temporarily unavailable."
)


def bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    """파싱된 Authorization 헤더를 공통 Bearer 인증 오류로 변환합니다."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise service.AuthError(
            401, service.AUTHENTICATION_REQUIRED, service.INVALID_TOKEN
        )
    return credentials.credentials


@router.post(
    "/sign-up",
    response_model=SuccessEnvelope[None],
    responses={
        200: documented_response(SuccessEnvelope[None], "정상 처리됨."),
        400: INVALID_REQUEST_RESPONSE,
        409: documented_response(
            UsernameConflictEnvelope, "The username is already in use."
        ),
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    openapi_extra={"security": []},
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
    response_model=SuccessEnvelope[TokenData],
    responses={
        200: documented_response(SuccessEnvelope[TokenData], "정상 처리됨."),
        400: INVALID_REQUEST_RESPONSE,
        401: documented_response(
            InvalidCredentialsEnvelope,
            "The username or password is incorrect.",
            authentication=True,
        ),
        429: documented_response(
            SignInRateLimitedEnvelope,
            "Too many sign-in attempts. Please try again later.",
            retry_after=True,
        ),
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    openapi_extra={"security": []},
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
    response_model=SuccessEnvelope[TokenData],
    responses={
        200: documented_response(SuccessEnvelope[TokenData], "정상 처리됨."),
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    openapi_extra={"security": []},
)
def refresh(payload: RefreshRequest, request: Request):
    """유효한 JWT로 새 토큰을 발급하고 실제 만료 정보를 반환합니다."""
    token = service.refresh(
        request.app.state.engine, request.app.state.settings, payload.token
    )
    return respond(200, security.token_data(token, request.app.state.settings))


@router.get(
    "/account",
    response_model=SuccessEnvelope[AccountData],
    responses={
        200: documented_response(SuccessEnvelope[AccountData], "정상 처리됨."),
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
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
    response_model=SuccessEnvelope[AccountData],
    responses={
        200: documented_response(
            SuccessEnvelope[AccountData], "본인 정보 수정이 완료되었습니다."
        ),
        400: INVALID_REQUEST_RESPONSE,
        401: documented_response(
            AuthenticationRequiredEnvelope | CurrentPasswordIncorrectEnvelope,
            "토큰이 유효하지 않거나 현재 비밀번호가 일치하지 않습니다.",
            authentication=True,
        ),
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
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
    response_model=SuccessEnvelope[None],
    responses={
        200: documented_response(SuccessEnvelope[None], "계정 삭제가 완료되었습니다."),
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
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
