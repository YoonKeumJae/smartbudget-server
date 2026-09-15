"""v1 계정 API와 비밀 없는 응답·오류 계약을 제공합니다."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, field_validator
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException

from accountbook import auth, security
from accountbook.config import Settings
from accountbook.database import build_engine

SUCCESS_MESSAGE = "The request has been accepted and processed."
TOKEN = Annotated[str, Field(strict=True, min_length=1, max_length=4096)]
NAME = Annotated[str, Field(strict=True, max_length=256)]
PASSWORD = Annotated[SecretStr, Field(strict=True, max_length=128)]


class Credentials(BaseModel):
    """가입·로그인이 공유하는 필수 문자열과 알 수 없는 필드 거부 규칙입니다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    username: Annotated[str, Field(min_length=4, max_length=12)]
    password: PASSWORD

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        """HTTP 입력에도 공통 아이디 정규화 정책을 적용합니다."""
        return security.normalize_username(value)


class Registration(Credentials):
    """회원가입에 필수 표시 이름을 추가합니다."""

    display_name: NAME


class RefreshRequest(BaseModel):
    """갱신 JWT는 JSON 본문의 token에서만 받습니다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    token: TOKEN


class AccountUpdate(BaseModel):
    """선택 수정값의 생략과 명시적 null을 구별합니다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    token: TOKEN | None = None
    password: PASSWORD | None = None
    display_name: NAME | None = None
    budget_limit: Annotated[StrictInt, Field(ge=0, le=10000000)] | None = None

    @field_validator("password", "display_name")
    @classmethod
    def reject_null(cls, value):
        """생략은 허용하지만 비밀번호·표시 이름의 명시 null은 거부합니다."""
        if value is None:
            raise ValueError("Invalid null value")
        return value


class TokenData(BaseModel):
    """로그인·갱신의 JWT 단일 출력 필드를 문서화합니다."""

    token: str


class AccountData(BaseModel):
    """본인 계정 조회의 표시 이름과 nullable 월 예산을 문서화합니다."""

    display_name: str
    budget_limit: int | None


class Envelope[T](BaseModel):
    """API 전체의 HTTP 상태·영문 메시지·데이터 봉투를 문서화합니다."""

    status: int
    message: str
    data: T


ERROR_RESPONSES = {
    code: {"model": Envelope[None], "description": description}
    for code, description in [
        (400, "Invalid request"),
        (401, "Authentication failed"),
        (409, "Username already exists"),
        (429, "Sign-in retry limit"),
        (503, "Service temporarily unavailable"),
    ]
}


def respond(
    status: int,
    data: dict | None = None,
    message: str = SUCCESS_MESSAGE,
    headers: dict | None = None,
) -> JSONResponse:
    """HTTP 상태와 일치하는 공개 JSON 봉투를 캐시 없이 반환합니다."""
    return JSONResponse(
        {"status": status, "message": message, "data": data},
        status_code=status,
        headers={"Cache-Control": "no-store", **(headers or {})},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """설정과 독립 엔진을 가진 FastAPI 앱의 수명 및 라우트를 구성합니다."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """앱 시작에 DB를 초기화하고 종료에 엔진을 반환합니다."""
        app.state.engine = build_engine(settings.database_path)
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(title="AccountBook API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings

    @app.middleware("http")
    async def enforce_transport(request: Request, call_next):
        """인증 토큰의 위치 혼용과 비JSON 본문 및 GET 본문을 거부합니다."""
        if request.url.path.startswith("/api/v1/auth/"):
            if request.query_params:
                return respond(400, message=auth.INVALID_REQUEST)
            if request.method == "GET" and await request.body():
                return respond(400, message=auth.INVALID_REQUEST)
            if request.method in {"POST", "PUT"}:
                if (
                    request.headers.get("content-type", "")
                    .split(";")[0]
                    .strip()
                    .lower()
                    != "application/json"
                ):
                    return respond(400, message=auth.INVALID_REQUEST)
                if (
                    request.url.path.endswith(("/refresh", "/account"))
                    and "authorization" in request.headers
                ):
                    return respond(400, message=auth.INVALID_REQUEST)
                if request.method == "PUT" and request.url.path.endswith("/account"):
                    try:
                        payload = await request.json()
                    except ValueError:
                        return respond(400, message=auth.INVALID_REQUEST)
                    if isinstance(payload, dict) and payload.get("token") in (None, ""):
                        return respond(
                            401,
                            message=auth.INVALID_TOKEN,
                            headers={"WWW-Authenticate": "Bearer"},
                        )
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        """Pydantic 오류의 원래 입력을 노출하지 않고 400 봉투를 반환합니다."""
        return respond(400, message=auth.INVALID_REQUEST)

    @app.exception_handler(ValueError)
    async def invalid_value(request: Request, error: ValueError):
        """공통 입력 정책 실패를 비밀 없는 요청 오류로 반환합니다."""
        return respond(400, message=auth.INVALID_REQUEST)

    @app.exception_handler(auth.AuthError)
    async def auth_error(request: Request, error: auth.AuthError):
        """인증 실패와 차단 상태를 HTTP 계약의 헤더와 함께 반환합니다."""
        headers = {}
        if error.status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        if error.retry_after is not None:
            headers["Retry-After"] = str(error.retry_after)
        return respond(error.status_code, message=error.message, headers=headers)

    @app.exception_handler(OperationalError)
    async def database_error(request: Request, error: OperationalError):
        """DB 잠금·사용 불가의 내부 경로를 숨기고 일시 실패를 반환합니다."""
        return respond(503, message="The service is temporarily unavailable.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        """라우트 오류도 같은 JSON 봉투를 사용하게 합니다."""
        return respond(
            error.status_code, message="The requested operation is not available."
        )

    @app.post(
        "/api/v1/auth/sign-up",
        response_model=Envelope[None],
        responses={code: ERROR_RESPONSES[code] for code in [400, 409, 503]},
    )
    def sign_up(payload: Registration):
        """필수 이름·아이디·비밀번호로 계정을 생성합니다."""
        auth.register(
            app.state.engine,
            payload.username,
            payload.password.get_secret_value(),
            payload.display_name,
        )
        return respond(200)

    @app.post(
        "/api/v1/auth/sign-in",
        response_model=Envelope[TokenData],
        responses={code: ERROR_RESPONSES[code] for code in [400, 401, 429, 503]},
    )
    def sign_in(payload: Credentials):
        """로그인 제한을 적용하고 data.token 한 개를 반환합니다."""
        token = auth.sign_in(
            app.state.engine,
            settings,
            payload.username,
            payload.password.get_secret_value(),
        )
        return respond(200, {"token": token})

    @app.post(
        "/api/v1/auth/refresh",
        response_model=Envelope[TokenData],
        responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
    )
    def refresh(payload: RefreshRequest):
        """만료되지 않은 JWT로 새 유효기간의 JWT를 발급합니다."""
        return respond(
            200, {"token": auth.refresh(app.state.engine, settings, payload.token)}
        )

    @app.get(
        "/api/v1/auth/account",
        response_model=Envelope[AccountData],
        responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
    )
    def get_account(request: Request):
        """Authorization Bearer로 인증된 본인의 정보만 반환합니다."""
        parts = request.headers.get("authorization", "").split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise auth.AuthError(401, auth.INVALID_TOKEN)
        return respond(200, auth.get_account(app.state.engine, settings, parts[1]))

    @app.put(
        "/api/v1/auth/account",
        response_model=Envelope[None],
        responses={code: ERROR_RESPONSES[code] for code in [400, 401, 503]},
    )
    def update_account(payload: AccountUpdate):
        """JSON token을 검증해 제공된 본인 정보만 원자적으로 수정합니다."""
        if payload.token is None:
            raise auth.AuthError(401, auth.INVALID_TOKEN)
        changes = payload.model_dump(exclude_unset=True)
        changes.pop("token")
        if "password" in changes:
            changes["password"] = changes["password"].get_secret_value()
        auth.update_account(app.state.engine, settings, payload.token, changes)
        return respond(200)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Retry-After"],
    )

    def openapi():
        """생성된 OpenAPI를 실제 봉투 응답과 400 입력 오류 계약에 맞춥니다."""
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title, version=app.version, routes=app.routes
            )
            for path, methods in schema["paths"].items():
                for method, operation in methods.items():
                    responses = operation["responses"]
                    responses.pop("422", None)
                    if method == "get" and path.endswith("/account"):
                        operation["parameters"] = [
                            {
                                "name": "Authorization",
                                "in": "header",
                                "required": True,
                                "schema": {"type": "string"},
                                "description": "Bearer <JWT>",
                            }
                        ]
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi
    return app
