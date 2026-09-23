"""OpenAPI 월별 예산 엔드포인트의 구현 대기 라우트를 등록합니다."""

from typing import Annotated

from fastapi import APIRouter, Path, Security
from fastapi.security import HTTPAuthorizationCredentials

from smartbudget_server.auth.router import bearer
from smartbudget_server.http import documented_response
from smartbudget_server.monthly_budget.schemas import (
    AuthenticationRequiredEnvelope,
    InvalidRequestEnvelope,
    MonthlyBudgetWrite,
    ServiceUnavailableEnvelope,
    SuccessEnvelope,
)

router = APIRouter(prefix="/api/v1/monthly-budget", tags=["월별 예산"])

RESPONSES = {
    400: documented_response(
        InvalidRequestEnvelope, "month 또는 amount 형식이 잘못되었습니다."
    ),
    401: documented_response(
        AuthenticationRequiredEnvelope, "Bearer 인증이 필요합니다.", authentication=True
    ),
    503: documented_response(
        ServiceUnavailableEnvelope, "DB를 일시적으로 사용할 수 없습니다."
    ),
}


@router.get(
    "/{month}",
    response_model=SuccessEnvelope,
    responses=RESPONSES,
    summary="월별 예산 조회",
    operation_id="get_api_v1_monthly_budget_month",
)
def get_monthly_budget(
    month: Annotated[str, Path(pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """인증 사용자의 대상 월 예산을 조회하는 구현 지점을 제공합니다."""
    raise NotImplementedError


@router.put(
    "/{month}",
    response_model=SuccessEnvelope,
    responses=RESPONSES,
    summary="월별 예산 저장",
    operation_id="put_api_v1_monthly_budget_month",
)
def put_monthly_budget(
    month: Annotated[str, Path(pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")],
    payload: MonthlyBudgetWrite,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer)
    ] = None,
):
    """인증 사용자의 대상 월 예산을 저장하는 구현 지점을 제공합니다."""
    raise NotImplementedError
