"""OpenAPI 영수증 OCR 프록시 엔드포인트의 구현 대기 라우트를 등록합니다."""

from typing import Annotated

from fastapi import APIRouter, Header, Request, Security
from fastapi.security import HTTPAuthorizationCredentials

from smartbudget_server.auth.router import bearer
from smartbudget_server.http import documented_response
from smartbudget_server.proxy.schemas import (
    AuthenticationRequiredEnvelope,
    IdempotencyConflictEnvelope,
    InternalErrorEnvelope,
    InvalidRequestEnvelope,
    SuccessEnvelope,
)

router = APIRouter(prefix="/api/v1/proxy", tags=["외부 API 프록시"])

OCR_REQUEST_BODY = {
    "requestBody": {
        "required": True,
        "description": (
            "multipart/form-data의 files 필드에 JPEG, PNG, HEIC 또는 PDF "
            "파일 1~10개를 첨부합니다. 파일당 최대 크기는 10,000,000바이트입니다."
        ),
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["files"],
                    "properties": {
                        "files": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 10,
                            "items": {"type": "string", "format": "binary"},
                        }
                    },
                    "additionalProperties": False,
                }
            }
        },
    }
}


@router.post(
    "/ocr",
    response_model=SuccessEnvelope,
    responses={
        400: documented_response(
            InvalidRequestEnvelope, "업로드 요청이 잘못되었습니다."
        ),
        401: documented_response(
            AuthenticationRequiredEnvelope,
            "Bearer 인증이 필요합니다.",
            authentication=True,
        ),
        409: documented_response(
            IdempotencyConflictEnvelope, "중복 방지 키가 충돌했습니다."
        ),
        500: documented_response(
            InternalErrorEnvelope, "OCR 결과를 구성하지 못했습니다."
        ),
    },
    operation_id="post_api_v1_proxy_ocr",
    summary="OCR API 프록시",
    openapi_extra=OCR_REQUEST_BODY,
)
async def proxy_ocr(
    request: Request,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
        ),
    ] = None,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """영수증 파일을 외부 OCR로 전달하는 구현 지점을 제공합니다."""
    raise NotImplementedError
