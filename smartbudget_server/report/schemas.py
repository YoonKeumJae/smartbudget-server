"""소비 분석 API의 요청 검증과 응답 데이터 스키마를 정의합니다."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from smartbudget_server.http import SUCCESS_MESSAGE, Envelope, response_code_schema

DateString = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]
DateTimeString = Annotated[
    str,
    Field(
        pattern=(
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):"
            r"[0-5][0-9]:[0-5][0-9]\+09:00$"
        )
    ),
]


class PeriodType(StrEnum):
    """리포트가 집계하는 일·주·월·연 기간 단위입니다."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ReportRequest(BaseModel):
    """생성할 리포트의 기간 종류와 시작 날짜를 검증합니다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    period_type: PeriodType
    period_start: DateString


class ReportSummary(BaseModel):
    """리포트 목록에 필요한 기간·생성 시각·최신 상태를 반환합니다."""

    model_config = ConfigDict(extra="forbid")
    id: Annotated[int, Field(ge=1)]
    generated_at: DateTimeString
    period_type: PeriodType
    period_start: DateString
    period_end: DateString
    is_stale: bool


class ReportDetail(ReportSummary):
    """리포트 요약에 LLM이 생성한 전체 분석 내용을 더합니다."""

    full_report: Annotated[str, Field(min_length=1)]


class GeneratedReport(ReportDetail):
    """방금 생성한 리포트에 요청 시각과 처리 시간을 더합니다."""

    requested_at: DateTimeString
    processing_time_ms: Annotated[int, Field(ge=0)]
    is_stale: Literal[False]


class ReportPage(BaseModel):
    """커서 기반 리포트 목록과 다음 페이지 위치를 반환합니다."""

    model_config = ConfigDict(extra="forbid")
    items: list[ReportSummary]
    next_cursor: str | None


class SuccessEnvelope[T](Envelope[T]):
    """소비 분석 API의 200 성공 응답 봉투를 정의합니다."""

    status: Literal[200]
    code: Annotated[Literal["SUCCESS"], response_code_schema("SUCCESS")]
    message: Literal[SUCCESS_MESSAGE]


class InvalidRequestEnvelope(Envelope[None]):
    """분석 기간 또는 요청 형식이 잘못된 응답 봉투입니다."""

    status: Literal[400]
    code: Literal["INVALID_REQUEST", "REPORT_NO_TRANSACTIONS"]
    message: str


class AuthenticationRequiredEnvelope(Envelope[None]):
    """소비 분석 API의 Bearer 인증 실패 응답 봉투입니다."""

    status: Literal[401]
    code: Annotated[
        Literal["AUTHENTICATION_REQUIRED"],
        response_code_schema("AUTHENTICATION_REQUIRED"),
    ]
    message: str


class ResourceNotFoundEnvelope(Envelope[None]):
    """본인 소유 리포트를 찾지 못한 경우의 응답 봉투입니다."""

    status: Literal[404]
    code: Annotated[
        Literal["RESOURCE_NOT_FOUND"], response_code_schema("RESOURCE_NOT_FOUND")
    ]
    message: str


class IdempotencyConflictEnvelope(Envelope[None]):
    """중복 방지 키 또는 같은 기간 생성 작업 충돌 응답입니다."""

    status: Literal[409]
    code: Literal[
        "IDEMPOTENCY_KEY_CONFLICT",
        "IDEMPOTENCY_REQUEST_IN_PROGRESS",
        "REPORT_GENERATION_IN_PROGRESS",
    ]
    message: str


class ProviderErrorEnvelope(Envelope[None]):
    """외부 LLM 호출 실패의 502 응답 봉투입니다."""

    status: Literal[502]
    code: Literal["REPORT_PROVIDER_ERROR"]
    message: str


class ServiceUnavailableEnvelope(Envelope[None]):
    """리포트 저장소를 일시적으로 사용할 수 없는 응답 봉투입니다."""

    status: Literal[503]
    code: Annotated[
        Literal["SERVICE_UNAVAILABLE"], response_code_schema("SERVICE_UNAVAILABLE")
    ]
    message: str


class ProviderTimeoutEnvelope(Envelope[None]):
    """외부 LLM 제한 시간 초과의 504 응답 봉투입니다."""

    status: Literal[504]
    code: Literal["REPORT_PROVIDER_TIMEOUT"]
    message: str
