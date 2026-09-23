"""OpenAPI 거래 엔드포인트의 구현 대기 라우트를 등록합니다."""

from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from smartbudget_server.auth.router import bearer
from smartbudget_server.http import documented_response
from smartbudget_server.transaction.schemas import (
    AuthenticationRequiredEnvelope,
    CreatedEnvelope,
    IdempotencyConflictEnvelope,
    InvalidRequestEnvelope,
    ResourceNotFoundEnvelope,
    ServiceUnavailableEnvelope,
    SuccessEnvelope,
    TransactionCreate,
    TransactionData,
    TransactionPage,
    TransactionUpdate,
)

router = APIRouter(prefix="/api/v1/transaction", tags=["거래"])

INVALID_REQUEST_RESPONSE = documented_response(
    InvalidRequestEnvelope, "잘못된 요청입니다."
)
AUTHENTICATION_REQUIRED_RESPONSE = documented_response(
    AuthenticationRequiredEnvelope, "Bearer 인증이 필요합니다.", authentication=True
)
SERVICE_UNAVAILABLE_RESPONSE = documented_response(
    ServiceUnavailableEnvelope, "DB를 일시적으로 사용할 수 없습니다."
)
NOT_FOUND_RESPONSE = documented_response(
    ResourceNotFoundEnvelope, "본인 소유 거래를 찾을 수 없습니다."
)


@router.get(
    "",
    response_model=SuccessEnvelope[TransactionPage],
    responses={
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    summary="거래 목록 조회",
    operation_id="get_api_v1_transaction",
)
def list_transaction(
    start_date: Annotated[
        str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    ] = None,
    end_date: Annotated[
        str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    ] = None,
    limit: Annotated[int, Query(strict=True, ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """인증 사용자의 거래 목록을 조회하는 구현 지점을 제공합니다."""
    raise NotImplementedError


@router.post(
    "",
    response_model=CreatedEnvelope,
    status_code=201,
    responses={
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        409: documented_response(
            IdempotencyConflictEnvelope, "중복 방지 키가 충돌했습니다."
        ),
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    summary="거래 생성",
    operation_id="post_api_v1_transaction",
)
def create_transaction(
    payload: TransactionCreate,
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
    """검증된 거래를 생성하는 구현 지점을 제공합니다."""
    raise NotImplementedError


@router.get(
    "/{id}",
    response_model=SuccessEnvelope[TransactionData],
    responses={
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    summary="거래 상세 조회",
    operation_id="get_api_v1_transaction_id",
)
def get_transaction(
    id: Annotated[int, Path(ge=1)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """본인 소유 거래 한 건을 조회하는 구현 지점을 제공합니다."""
    raise NotImplementedError


@router.patch(
    "/{id}",
    response_model=SuccessEnvelope[TransactionData],
    responses={
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    summary="거래 수정",
    operation_id="patch_api_v1_transaction_id",
)
def update_transaction(
    id: Annotated[int, Path(ge=1)],
    payload: TransactionUpdate,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """본인 소유 거래를 수정하는 구현 지점을 제공합니다."""
    raise NotImplementedError


@router.delete(
    "/{id}",
    response_model=SuccessEnvelope[None],
    responses={
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    summary="거래 삭제",
    operation_id="delete_api_v1_transaction_id",
)
def delete_transaction(
    id: Annotated[int, Path(ge=1)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """본인 소유 거래를 삭제하는 구현 지점을 제공합니다."""
    raise NotImplementedError
