"""인증 라우트의 요청 검증과 응답 데이터 스키마를 정의합니다."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, field_validator

from accountbook.auth import security

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
