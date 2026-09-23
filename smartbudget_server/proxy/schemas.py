"""영수증 OCR 프록시 API의 응답 데이터 스키마를 정의합니다."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smartbudget_server.http import SUCCESS_MESSAGE, Envelope, response_code_schema


class OcrStatus(StrEnum):
    """파일별 OCR 처리의 성공 또는 실패 상태입니다."""

    SUCCESS = "success"
    FAILED = "failed"


class OcrResult(BaseModel):
    """업로드 순서대로 반환하는 파일별 OCR 인식 결과입니다."""

    model_config = ConfigDict(extra="forbid")
    file_name: Annotated[str, Field(min_length=1)]
    status: OcrStatus
    error_message: str | None
    store_name: str | None
    items: list[str] = Field(default_factory=list)
    date: Annotated[str | None, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]
    time: Annotated[
        str | None,
        Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$"),
    ]
    amount: Annotated[int | None, Field(ge=1)]
    file_index: Annotated[int, Field(ge=0, le=9)]

    @model_validator(mode="after")
    def validate_status_fields(self):
        """성공과 실패 상태에 맞는 오류 및 인식 필드 조합을 강제합니다."""
        if self.status == OcrStatus.SUCCESS and self.error_message is not None:
            raise ValueError("Successful OCR results cannot contain an error")
        if self.status == OcrStatus.FAILED:
            if not self.error_message:
                raise ValueError("Failed OCR results require an error")
            if self.items or any(
                value is not None
                for value in (self.store_name, self.date, self.time, self.amount)
            ):
                raise ValueError("Failed OCR results cannot contain recognized data")
        return self


OcrResults = Annotated[list[OcrResult], Field(min_length=1, max_length=10)]


class SuccessEnvelope(Envelope[OcrResults]):
    """OCR 파일별 결과 배열을 담는 200 성공 응답 봉투입니다."""

    status: Literal[200]
    code: Annotated[Literal["SUCCESS"], response_code_schema("SUCCESS")]
    message: Literal[SUCCESS_MESSAGE]


class InvalidRequestEnvelope(Envelope[None]):
    """파일 개수·형식·크기 또는 요청 형식 오류 응답 봉투입니다."""

    status: Literal[400]
    code: Annotated[Literal["INVALID_REQUEST"], response_code_schema("INVALID_REQUEST")]
    message: str


class AuthenticationRequiredEnvelope(Envelope[None]):
    """OCR 프록시의 Bearer 인증 실패 응답 봉투입니다."""

    status: Literal[401]
    code: Annotated[
        Literal["AUTHENTICATION_REQUIRED"],
        response_code_schema("AUTHENTICATION_REQUIRED"),
    ]
    message: str


class IdempotencyConflictEnvelope(Envelope[None]):
    """OCR 중복 방지 키 충돌 또는 진행 중 요청의 응답 봉투입니다."""

    status: Literal[409]
    code: Literal["IDEMPOTENCY_KEY_CONFLICT", "IDEMPOTENCY_REQUEST_IN_PROGRESS"]
    message: str


class InternalErrorEnvelope(Envelope[None]):
    """파일별 결과를 구성할 수 없는 서버 오류 응답 봉투입니다."""

    status: Literal[500]
    code: Annotated[Literal["INTERNAL_ERROR"], response_code_schema("INTERNAL_ERROR")]
    message: str
