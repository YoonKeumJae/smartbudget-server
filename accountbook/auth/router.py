"""인증 라우트와 이 기능의 토큰 전달·인증 오류 규칙을 등록합니다."""

from fastapi import APIRouter, FastAPI, Request

from accountbook.auth import service
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
    """로그인 제한을 적용하고 data.token 한 개를 반환합니다."""
    token = service.sign_in(
        request.app.state.engine,
        request.app.state.settings,
        payload.username,
        payload.password.get_secret_value(),
    )
    return respond(200, {"token": token})


@router.post(
    "/refresh",
    response_model=Envelope[TokenData],
    responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
)
def refresh(payload: RefreshRequest, request: Request):
    """만료되지 않은 JWT로 새 유효기간의 JWT를 발급합니다."""
    return respond(
        200,
        {
            "token": service.refresh(
                request.app.state.engine, request.app.state.settings, payload.token
            )
        },
    )


@router.get(
    "/account",
    response_model=Envelope[AccountData],
    openapi_extra={
        "parameters": [
            {
                "name": "Authorization",
                "in": "header",
                "required": True,
                "schema": {"type": "string"},
                "description": "Bearer <JWT>",
            }
        ]
    },
    responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
)
def get_account(request: Request):
    """Authorization Bearer로 인증된 본인의 정보만 반환합니다."""
    parts = request.headers.get("authorization", "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise service.AuthError(401, service.INVALID_TOKEN)
    return respond(
        200,
        service.get_account(
            request.app.state.engine, request.app.state.settings, parts[1]
        ),
    )


@router.put(
    "/account",
    response_model=Envelope[None],
    responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
)
def update_account(payload: AccountUpdate, request: Request):
    """JSON token을 검증해 제공된 본인 정보만 원자적으로 수정합니다."""
    if payload.token is None:
        raise service.AuthError(401, service.INVALID_TOKEN)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("token")
    if "password" in changes:
        changes["password"] = changes["password"].get_secret_value()
    service.update_account(
        request.app.state.engine, request.app.state.settings, payload.token, changes
    )
    return respond(200)


def configure_auth(app: FastAPI) -> None:
    """앱에 인증 전송 규칙·인증 오류 처리와 라우터를 함께 등록합니다."""

    @app.middleware("http")
    async def enforce_transport(request: Request, call_next):
        """인증 토큰의 위치 혼용과 비JSON 본문 및 GET 본문을 거부합니다."""
        if request.url.path.startswith("/api/v1/auth/"):
            if request.query_params:
                return respond(400, message=INVALID_REQUEST)
            if request.method == "GET" and await request.body():
                return respond(400, message=INVALID_REQUEST)
            if request.method in {"POST", "PUT"}:
                if (
                    request.headers.get("content-type", "")
                    .split(";")[0]
                    .strip()
                    .lower()
                    != "application/json"
                ):
                    return respond(400, message=INVALID_REQUEST)
                if (
                    request.url.path.endswith(("/refresh", "/account"))
                    and "authorization" in request.headers
                ):
                    return respond(400, message=INVALID_REQUEST)
                if request.method == "PUT" and request.url.path.endswith("/account"):
                    try:
                        payload = await request.json()
                    except ValueError:
                        return respond(400, message=INVALID_REQUEST)
                    if isinstance(payload, dict) and payload.get("token") in (None, ""):
                        return respond(
                            401,
                            message=service.INVALID_TOKEN,
                            headers={"WWW-Authenticate": "Bearer"},
                        )
        return await call_next(request)

    @app.exception_handler(service.AuthError)
    async def auth_error(request: Request, error: service.AuthError):
        """인증 실패와 차단 상태를 HTTP 계약의 헤더와 함께 반환합니다."""
        headers = {}
        if error.status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        if error.retry_after is not None:
            headers["Retry-After"] = str(error.retry_after)
        return respond(error.status_code, message=error.message, headers=headers)

    app.include_router(router)
