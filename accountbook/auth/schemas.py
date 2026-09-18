"""인증 라우트의 요청 검증과 응답 데이터 스키마를 정의합니다."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from accountbook.auth import security, service
from accountbook.http import (
    INVALID_REQUEST,
    SUCCESS_MESSAGE,
    Envelope,
    response_code_schema,
)

TOKEN = Annotated[
    str,
    Field(strict=True, min_length=1, max_length=4096),
    WithJsonSchema(
        {
            "type": "string",
            "minLength": 1,
            "maxLength": 4096,
            "description": (
                "요청 JSON에 첨부할 유효한 JWT입니다. 토큰 수명·검증 정책은 "
                "API 설명을 참고합니다."
            ),
            "writeOnly": True,
        }
    ),
]
NAME = Annotated[str, Field(strict=True, max_length=256)]
PASSWORD = Annotated[SecretStr, Field(strict=True, max_length=128)]
CURRENT_PASSWORD = Annotated[
    SecretStr, Field(strict=True, min_length=1, max_length=128)
]

NEW_PASSWORD_SCHEMA = WithJsonSchema(
    {
        "type": "string",
        "minLength": 8,
        "maxLength": 20,
        "format": "password",
        "writeOnly": True,
        "pattern": (
            r"^(?:(?=.*[A-Za-z])(?=.*[0-9])|"
            r"(?=.*[A-Za-z])(?=.*[!@#$%^&*_=+?\-])|"
            r"(?=.*[0-9])(?=.*[!@#$%^&*_=+?\-]))"
            r"[A-Za-z0-9!@#$%^&*_=+?\-]{8,20}(?![\s\S])"
        ),
        "description": (
            "비밀번호: 8–20자, `A–Z`, `a–z`, `0–9`, `!@#$%^&*_-+=?`만 "
            "허용합니다. 영문·숫자·특수문자 세 종류 중 두 종류 이상이 "
            "필요합니다. 대소문자를 구분하며 공백·한글·그 외 문자를 "
            "거부합니다. 가입·비밀번호 변경에 이 정책을 적용하며, 로그인은 "
            "입력한 비밀번호를 해시와 비교합니다."
        ),
    }
)
DISPLAY_NAME_SCHEMA = WithJsonSchema(
    {
        "type": "string",
        "pattern": (
            r"^ *[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ]"
            r"[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ ]{0,8}"
            r"[A-Za-z0-9가-힣ㄱ-ㆎᄀ-ᇿ] *(?![\s\S])"
        ),
        "description": (
            "표시 이름: 일반 공백을 앞뒤에서 제거한 후 2–10자입니다. 한글 "
            "음절·자모, ASCII 영문·숫자·일반 공백만 허용합니다. 중간 공백을 "
            "유지하고 글자 수에 포함합니다. 공백만 있는 이름·탭·줄바꿈·"
            "제어문자·다른 특수문자를 거부합니다. 중복은 허용합니다. 원본 "
            "입력은 앞뒤 공백을 포함하여 최대 256자이며, 공백 제거 후 2–10자 "
            "제한은 pattern으로 검사합니다."
        ),
        "maxLength": 256,
    }
)


class Credentials(BaseModel):
    """가입·로그인이 공유하는 필수 문자열과 알 수 없는 필드 거부 규칙입니다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    username: Annotated[
        str,
        Field(
            min_length=4,
            max_length=12,
            description=(
                "아이디: 4–12자, ASCII 영문·숫자만 허용합니다. 소문자로 저장하여 "
                "대소문자를 구분하지 않습니다. 공백을 자동 제거하지 않습니다."
            ),
            json_schema_extra={"pattern": r"^[A-Za-z0-9]{4,12}(?![\s\S])"},
        ),
    ]
    password: Annotated[
        PASSWORD,
        Field(
            description=(
                "평문 비밀번호를 저장된 해시와 비교합니다. 가입·변경의 조합 정책은 "
                "로그인에 적용하지 않습니다. 로그인 원본 입력의 최대 길이는 128자입니다."
            ),
        ),
    ]

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        """HTTP 입력에도 공통 아이디 정규화 정책을 적용합니다."""
        return security.normalize_username(value)


class Registration(Credentials):
    """회원가입 필수 입력과 가입·수정 공통 비밀번호·이름 계약을 공개합니다."""

    password: Annotated[PASSWORD, NEW_PASSWORD_SCHEMA]
    display_name: Annotated[NAME, DISPLAY_NAME_SCHEMA]


class RefreshRequest(BaseModel):
    """갱신 JWT는 JSON 본문의 token에서만 받습니다."""

    model_config = ConfigDict(extra="forbid", strict=True)
    token: TOKEN


class AccountUpdate(BaseModel):
    """계정 변경값과 현재·새 비밀번호 쌍의 HTTP 입력 계약을 검증합니다."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "minProperties": 1,
            "dependentRequired": {
                "password": ["current_password"],
                "current_password": ["password"],
            },
        },
    )
    password: Annotated[
        PASSWORD | None,
        NEW_PASSWORD_SCHEMA,
    ] = None
    display_name: Annotated[
        NAME | None,
        DISPLAY_NAME_SCHEMA,
    ] = None
    current_password: Annotated[
        CURRENT_PASSWORD | None,
        WithJsonSchema(
            {
                "type": "string",
                "minLength": 1,
                "maxLength": 128,
                "format": "password",
                "writeOnly": True,
                "description": (
                    "password를 바꿀 때 확인할 현재 비밀번호입니다. password와 함께 "
                    "전달해야 합니다."
                ),
            }
        ),
    ] = None

    @field_validator("password", "display_name", "current_password")
    @classmethod
    def reject_null(cls, value):
        """생략은 허용하지만 수정 필드의 명시적 null은 거부합니다."""
        if value is None:
            raise ValueError("Invalid null value")
        return value

    @model_validator(mode="after")
    def validate_changes(self):
        """실제 변경과 현재·새 비밀번호의 완전한 쌍만 허용합니다."""
        supplied = self.model_fields_set
        if not supplied or supplied == {"current_password"}:
            raise ValueError("Invalid account update")
        if ("password" in supplied) != ("current_password" in supplied):
            raise ValueError("Invalid password pair")
        return self


class TokenData(BaseModel):
    """로그인·갱신의 JWT와 실제 만료 정보를 문서화합니다."""

    model_config = ConfigDict(extra="forbid")
    token: Annotated[str, Field(description="새로 발급한 JWT입니다.")]
    expires_at: Annotated[
        str,
        Field(
            description=(
                "발급한 JWT가 만료되는 한국 시간입니다. JWT의 exp와 같은 시점입니다."
            ),
            json_schema_extra={
                "format": "date-time",
                "pattern": (
                    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):"
                    r"[0-5][0-9]:[0-5][0-9]\+09:00(?![\s\S])"
                ),
                "example": "2026-09-21T14:30:00+09:00",
            },
        ),
    ]
    token_type: Annotated[
        Literal["Bearer"],
        Field(description="Authorization 헤더에 사용할 인증 유형입니다."),
    ]


class AccountData(BaseModel):
    """본인 계정 조회·수정 응답의 표시 이름을 문서화합니다."""

    model_config = ConfigDict(extra="forbid")
    display_name: Annotated[str, Field(description="저장된 표시 이름입니다.")]


class SuccessEnvelope[T](Envelope[T]):
    """인증 API 성공 응답의 고정 상태·코드·메시지를 공개합니다."""

    status: Literal[200]
    code: Annotated[Literal["SUCCESS"], response_code_schema("SUCCESS")]
    message: Literal[SUCCESS_MESSAGE]


class InvalidRequestEnvelope(Envelope[None]):
    """잘못된 인증 API 요청의 고정 응답 계약을 공개합니다."""

    status: Literal[400]
    code: Annotated[Literal["INVALID_REQUEST"], response_code_schema("INVALID_REQUEST")]
    message: Literal[INVALID_REQUEST]


class InvalidCredentialsEnvelope(Envelope[None]):
    """아이디 또는 비밀번호 불일치 응답 계약을 공개합니다."""

    status: Literal[401]
    code: Annotated[
        Literal["INVALID_CREDENTIALS"], response_code_schema("INVALID_CREDENTIALS")
    ]
    message: Literal[service.INVALID_LOGIN]


class AuthenticationRequiredEnvelope(Envelope[None]):
    """Bearer JWT 인증 실패 응답 계약을 공개합니다."""

    status: Literal[401]
    code: Annotated[
        Literal["AUTHENTICATION_REQUIRED"],
        response_code_schema("AUTHENTICATION_REQUIRED"),
    ]
    message: Literal[service.INVALID_TOKEN]


class CurrentPasswordIncorrectEnvelope(Envelope[None]):
    """현재 비밀번호 불일치 응답 계약을 공개합니다."""

    status: Literal[401]
    code: Annotated[
        Literal["CURRENT_PASSWORD_INCORRECT"],
        response_code_schema("CURRENT_PASSWORD_INCORRECT"),
    ]
    message: Literal[service.CURRENT_PASSWORD_MESSAGE]


class UsernameConflictEnvelope(Envelope[None]):
    """대소문자 정규화 후 아이디 중복 응답 계약을 공개합니다."""

    status: Literal[409]
    code: Annotated[
        Literal["USERNAME_CONFLICT"], response_code_schema("USERNAME_CONFLICT")
    ]
    message: Literal["The username is already in use."]


class SignInRateLimitedEnvelope(Envelope[None]):
    """로그인 재시도 제한과 Retry-After 응답 계약을 공개합니다."""

    status: Literal[429]
    code: Annotated[
        Literal["SIGN_IN_RATE_LIMITED"], response_code_schema("SIGN_IN_RATE_LIMITED")
    ]
    message: Literal["Too many sign-in attempts. Please try again later."]


class ServiceUnavailableEnvelope(Envelope[None]):
    """SQLite 잠금·일시 사용 불가 응답 계약을 공개합니다."""

    status: Literal[503]
    code: Annotated[
        Literal["SERVICE_UNAVAILABLE"], response_code_schema("SERVICE_UNAVAILABLE")
    ]
    message: Literal["The service is temporarily unavailable."]
