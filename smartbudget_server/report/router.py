"""OpenAPI 소비 분석 엔드포인트의 구현 대기 라우트를 등록합니다."""

from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Security
from fastapi.security import HTTPAuthorizationCredentials

from smartbudget_server.auth.router import bearer
from smartbudget_server.http import documented_response
from smartbudget_server.report.schemas import (
    AuthenticationRequiredEnvelope,
    GeneratedReport,
    IdempotencyConflictEnvelope,
    InvalidRequestEnvelope,
    PeriodType,
    ProviderErrorEnvelope,
    ProviderTimeoutEnvelope,
    ReportDetail,
    ReportPage,
    ReportRequest,
    ResourceNotFoundEnvelope,
    ServiceUnavailableEnvelope,
    SuccessEnvelope,
)

router = APIRouter(prefix="/api/v1/report", tags=["소비 분석"])

INVALID_REQUEST_RESPONSE = documented_response(
    InvalidRequestEnvelope, "분석 요청이 잘못되었습니다."
)
AUTHENTICATION_REQUIRED_RESPONSE = documented_response(
    AuthenticationRequiredEnvelope, "Bearer 인증이 필요합니다.", authentication=True
)
SERVICE_UNAVAILABLE_RESPONSE = documented_response(
    ServiceUnavailableEnvelope, "DB를 일시적으로 사용할 수 없습니다."
)
NOT_FOUND_RESPONSE = documented_response(
    ResourceNotFoundEnvelope, "본인 소유 리포트를 찾을 수 없습니다."
)


@router.get(
    "",
    response_model=SuccessEnvelope[ReportPage],
    responses={
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    summary="분석 조회",
    operation_id="get_api_v1_report",
)
def list_report(
    period_type: Annotated[PeriodType | None, Query()] = None,
    period_start: Annotated[
        str | None, Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    ] = None,
    limit: Annotated[int, Query(strict=True, ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """인증 사용자의 소비 분석 목록을 조회하는 구현 지점을 제공합니다."""
    raise NotImplementedError


@router.post(
    "",
    response_model=SuccessEnvelope[GeneratedReport],
    responses={
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        409: documented_response(
            IdempotencyConflictEnvelope, "리포트 생성 요청이 충돌했습니다."
        ),
        502: documented_response(
            ProviderErrorEnvelope, "외부 LLM 호출에 실패했습니다."
        ),
        503: SERVICE_UNAVAILABLE_RESPONSE,
        504: documented_response(
            ProviderTimeoutEnvelope, "외부 LLM 호출 시간이 초과되었습니다."
        ),
    },
    summary="분석 요청",
    operation_id="post_api_v1_report",
)
def create_report(
    payload: ReportRequest,
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
    """지정 기간의 소비 분석을 생성하는 구현 지점을 제공합니다."""
    raise NotImplementedError


@router.get(
    "/{id}",
    response_model=SuccessEnvelope[ReportDetail],
    responses={
        400: INVALID_REQUEST_RESPONSE,
        401: AUTHENTICATION_REQUIRED_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        503: SERVICE_UNAVAILABLE_RESPONSE,
    },
    summary="분석 상세 조회",
    operation_id="get_api_v1_report_id",
)
def get_report(
    id: Annotated[int, Path(ge=1)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """본인 소유 소비 분석 한 건을 조회하는 구현 지점을 제공합니다."""
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
    summary="분석 삭제",
    operation_id="delete_api_v1_report_id",
)
def delete_report(
    id: Annotated[int, Path(ge=1)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """본인 소유 소비 분석을 삭제하는 구현 지점을 제공합니다."""
    raise NotImplementedError
