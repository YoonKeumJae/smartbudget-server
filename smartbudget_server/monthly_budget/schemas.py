"""월별 예산 API의 요청 검증과 응답 데이터 스키마를 정의합니다."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from smartbudget_server.http import SUCCESS_MESSAGE, Envelope, response_code_schema

Month = Annotated[str, Field(pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")]
BudgetAmount = Annotated[int, Field(strict=True, ge=0, le=10_000_000)]


class MonthlyBudgetWrite(BaseModel):
    """월별 예산 저장 또는 삭제를 나타내는 금액을 검증합니다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    amount: BudgetAmount | None


class MonthlyBudgetData(BaseModel):
    """대상 월과 저장된 예산 또는 미설정 상태를 반환합니다."""

    model_config = ConfigDict(extra="forbid")
    month: Month
    amount: BudgetAmount | None


class SuccessEnvelope(Envelope[MonthlyBudgetData]):
    """월별 예산 조회·저장의 200 성공 응답 봉투입니다."""

    status: Literal[200]
    code: Annotated[Literal["SUCCESS"], response_code_schema("SUCCESS")]
    message: Literal[SUCCESS_MESSAGE]


class InvalidRequestEnvelope(Envelope[None]):
    """월 또는 금액 형식이 잘못된 경우의 응답 봉투입니다."""

    status: Literal[400]
    code: Annotated[Literal["INVALID_REQUEST"], response_code_schema("INVALID_REQUEST")]
    message: str


class AuthenticationRequiredEnvelope(Envelope[None]):
    """월별 예산 API의 Bearer 인증 실패 응답 봉투입니다."""

    status: Literal[401]
    code: Annotated[
        Literal["AUTHENTICATION_REQUIRED"],
        response_code_schema("AUTHENTICATION_REQUIRED"),
    ]
    message: str


class ServiceUnavailableEnvelope(Envelope[None]):
    """월별 예산 저장소를 일시적으로 사용할 수 없는 응답 봉투입니다."""

    status: Literal[503]
    code: Annotated[
        Literal["SERVICE_UNAVAILABLE"], response_code_schema("SERVICE_UNAVAILABLE")
    ]
    message: str
