"""기능별 라우트가 공유하는 JSON 응답·오류 처리·OpenAPI를 구성합니다."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException

SUCCESS_MESSAGE = "The request has been accepted and processed."
INVALID_REQUEST = "The request parameters or format are invalid."


class Envelope[T](BaseModel):
    """API 전체의 상태·코드·메시지·데이터 봉투를 문서화합니다."""

    status: int
    code: str
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
    code: str = "SUCCESS",
    message: str = SUCCESS_MESSAGE,
    headers: dict | None = None,
) -> JSONResponse:
    """HTTP 상태와 안정적인 code가 포함된 공개 JSON 봉투를 반환합니다."""
    return JSONResponse(
        {"status": status, "code": code, "message": message, "data": data},
        status_code=status,
        headers={"Cache-Control": "no-store", **(headers or {})},
    )


def configure_http(app: FastAPI) -> None:
    """앱에 공통 오류 봉투와 실제 입력 오류 상태의 OpenAPI를 등록합니다."""

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        """Pydantic 오류의 원래 입력을 노출하지 않고 400 봉투를 반환합니다."""
        return respond(400, code="INVALID_REQUEST", message=INVALID_REQUEST)

    @app.exception_handler(ValueError)
    async def invalid_value(request: Request, error: ValueError):
        """공통 입력 정책 실패를 비밀 없는 요청 오류로 반환합니다."""
        return respond(400, code="INVALID_REQUEST", message=INVALID_REQUEST)

    @app.exception_handler(OperationalError)
    async def database_error(request: Request, error: OperationalError):
        """DB 잠금·사용 불가의 내부 경로를 숨기고 일시 실패를 반환합니다."""
        return respond(
            503,
            code="SERVICE_UNAVAILABLE",
            message="The service is temporarily unavailable.",
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        """라우트 오류도 같은 JSON 봉투를 사용하게 합니다."""
        return respond(
            error.status_code,
            code="INVALID_REQUEST",
            message="The requested operation is not available.",
        )

    def openapi():
        """생성된 OpenAPI를 실제 봉투 응답과 400 입력 오류 계약에 맞춥니다."""
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title, version=app.version, routes=app.routes
            )
            for methods in schema["paths"].values():
                for operation in methods.values():
                    responses = operation["responses"]
                    responses.pop("422", None)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi
