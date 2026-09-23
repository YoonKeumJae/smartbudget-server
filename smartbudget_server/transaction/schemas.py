"""거래 API의 요청 검증과 응답 데이터 스키마를 정의합니다."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smartbudget_server.http import SUCCESS_MESSAGE, Envelope, response_code_schema

DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
TIME_PATTERN = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$"
DATETIME_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):"
    r"[0-5][0-9]:[0-5][0-9]\+09:00$"
)

DateString = Annotated[str, Field(pattern=DATE_PATTERN)]
TimeString = Annotated[str, Field(pattern=TIME_PATTERN)]
DateTimeString = Annotated[str, Field(pattern=DATETIME_PATTERN)]
Amount = Annotated[int, Field(strict=True, ge=1, le=100_000_000)]
StoreName = Annotated[str, Field(max_length=200)]
Note = Annotated[str, Field(max_length=2000)]


class TransactionType(StrEnum):
    """거래가 지출인지 수입인지 구분하는 공개 문자열입니다."""

    EXPENSE = "expense"
    INCOME = "income"


class TransactionSource(StrEnum):
    """거래가 생성된 금융 연동·수기·OCR 출처를 구분합니다."""

    FINANCIAL_SYNC = "financial_sync"
    MANUAL = "manual"
    OCR = "ocr"


class ExpenseCategory(StrEnum):
    """지출 거래에 허용되는 고정 카테고리입니다."""

    FOOD = "food"
    TRANSPORT = "transport"
    SHOPPING = "shopping"
    HOUSING_UTILITIES = "housing_utilities"
    HEALTH = "health"
    LEISURE = "leisure"
    EDUCATION = "education"
    OTHER_EXPENSE = "other_expense"


class IncomeCategory(StrEnum):
    """수입 거래에 허용되는 고정 카테고리입니다."""

    SALARY = "salary"
    SIDE_INCOME = "side_income"
    INVESTMENT_INCOME = "investment_income"
    OTHER_INCOME = "other_income"


BudgetCategory = ExpenseCategory | IncomeCategory


class TransactionCreate(BaseModel):
    """새 거래의 필수 값과 선택 가능한 표시 정보를 검증합니다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    date: DateString
    type: TransactionType
    source: TransactionSource
    category: BudgetCategory
    store_name: StoreName | None = None
    note: Note | None = None
    amount: Amount
    time: TimeString | None = None

    @model_validator(mode="after")
    def validate_category(self):
        """거래 유형과 지출·수입 카테고리의 조합을 일치시킵니다."""
        if self.type == TransactionType.EXPENSE and not isinstance(
            self.category, ExpenseCategory
        ):
            raise ValueError("Expense transactions require an expense category")
        if self.type == TransactionType.INCOME and not isinstance(
            self.category, IncomeCategory
        ):
            raise ValueError("Income transactions require an income category")
        return self


class TransactionUpdate(BaseModel):
    """거래 수정에서 제공 가능한 필드와 유형 변경 규칙을 검증합니다."""

    model_config = ConfigDict(
        extra="forbid", strict=True, json_schema_extra={"minProperties": 1}
    )
    date: DateString | None = None
    type: TransactionType | None = None
    category: BudgetCategory | None = None
    store_name: StoreName | None = None
    note: Note | None = None
    amount: Amount | None = None
    time: TimeString | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        """빈 수정과 null 금지 필드 및 유형·카테고리 쌍을 거부합니다."""
        supplied = self.model_fields_set
        if not supplied:
            raise ValueError("At least one transaction field is required")
        for field in {"date", "type", "category", "amount"} & supplied:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if "type" in supplied and "category" not in supplied:
            raise ValueError("Changing type requires category")
        if self.type == TransactionType.EXPENSE and not isinstance(
            self.category, ExpenseCategory
        ):
            raise ValueError("Expense transactions require an expense category")
        if self.type == TransactionType.INCOME and not isinstance(
            self.category, IncomeCategory
        ):
            raise ValueError("Income transactions require an income category")
        return self


class TransactionData(BaseModel):
    """생성·조회·수정 응답에서 반환하는 저장된 거래입니다."""

    model_config = ConfigDict(extra="forbid")
    id: Annotated[int, Field(ge=1)]
    date: DateString
    type: TransactionType
    source: TransactionSource
    category: BudgetCategory
    store_name: StoreName | None
    note: Note | None
    amount: Amount
    time: TimeString | None
    created_at: DateTimeString
    updated_at: DateTimeString


class TransactionPage(BaseModel):
    """커서 기반 거래 목록과 다음 페이지 위치를 반환합니다."""

    model_config = ConfigDict(extra="forbid")
    items: list[TransactionData]
    next_cursor: str | None


class SuccessEnvelope[T](Envelope[T]):
    """거래 API의 200 성공 응답 봉투를 정의합니다."""

    status: Literal[200]
    code: Annotated[Literal["SUCCESS"], response_code_schema("SUCCESS")]
    message: Literal[SUCCESS_MESSAGE]


class CreatedEnvelope(Envelope[TransactionData]):
    """거래 생성의 201 성공 응답 봉투를 정의합니다."""

    status: Literal[201]
    code: Annotated[Literal["SUCCESS"], response_code_schema("SUCCESS")]
    message: Literal[SUCCESS_MESSAGE]


class InvalidRequestEnvelope(Envelope[None]):
    """거래 요청 형식이 잘못된 경우의 응답 봉투입니다."""

    status: Literal[400]
    code: Annotated[Literal["INVALID_REQUEST"], response_code_schema("INVALID_REQUEST")]
    message: str


class AuthenticationRequiredEnvelope(Envelope[None]):
    """거래 API의 Bearer 인증 실패 응답 봉투입니다."""

    status: Literal[401]
    code: Annotated[
        Literal["AUTHENTICATION_REQUIRED"],
        response_code_schema("AUTHENTICATION_REQUIRED"),
    ]
    message: str


class ResourceNotFoundEnvelope(Envelope[None]):
    """본인 소유 거래를 찾지 못한 경우의 응답 봉투입니다."""

    status: Literal[404]
    code: Annotated[
        Literal["RESOURCE_NOT_FOUND"], response_code_schema("RESOURCE_NOT_FOUND")
    ]
    message: str


class IdempotencyConflictEnvelope(Envelope[None]):
    """중복 방지 키 충돌 또는 진행 중 요청의 응답 봉투입니다."""

    status: Literal[409]
    code: Literal["IDEMPOTENCY_KEY_CONFLICT", "IDEMPOTENCY_REQUEST_IN_PROGRESS"]
    message: str


class ServiceUnavailableEnvelope(Envelope[None]):
    """거래 저장소가 일시적으로 사용 불가능한 응답 봉투입니다."""

    status: Literal[503]
    code: Annotated[
        Literal["SERVICE_UNAVAILABLE"], response_code_schema("SERVICE_UNAVAILABLE")
    ]
    message: str
