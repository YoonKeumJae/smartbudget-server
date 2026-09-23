"""버전 API의 빌드 정보와 응답 봉투 스키마를 정의합니다."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from accountbook.http import (
    INVALID_REQUEST,
    SUCCESS_MESSAGE,
    Envelope,
    response_code_schema,
)


class BuildChannel(StrEnum):
    """서버가 직접 실행 또는 로컬·원격 이미지로 제공되는 채널을 구분합니다."""

    LOCAL_DIRECT = "local_direct"
    LOCAL_DOCKER = "local_docker"
    REMOTE_REGISTRY = "remote_registry"


class VersionData(BaseModel):
    """클라이언트가 실행 중인 서버 빌드를 식별할 공개 메타데이터입니다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    build_timestamp: Annotated[
        datetime,
        Field(
            description="이미지 빌드 또는 로컬 애플리케이션 생성 일시입니다.",
            examples=["2026-09-23T21:30:00+09:00"],
        ),
    ]
    version: Annotated[
        str,
        Field(
            pattern=(r"^(?:[0-9a-f]{40}|[0-9a-f]{64}|sha256:[0-9a-f]{64}|unknown)$"),
            description="Git 커밋 해시 또는 Docker 이미지 해시입니다.",
        ),
    ]
    channel: Annotated[
        BuildChannel,
        Field(description="서버 빌드가 제공된 채널입니다."),
    ]

    @field_validator("build_timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """빌드 일시에 UTC 오프셋이 반드시 포함되도록 검증합니다."""
        if value.utcoffset() is None:
            raise ValueError("Build timestamp must include a UTC offset")
        return value


class VersionSuccessEnvelope(Envelope[VersionData]):
    """버전 조회 성공 응답의 고정 상태·코드·메시지를 공개합니다."""

    status: Literal[200]
    code: Annotated[Literal["SUCCESS"], response_code_schema("SUCCESS")]
    message: Literal[SUCCESS_MESSAGE]


class VersionInvalidRequestEnvelope(Envelope[None]):
    """버전 조회에 허용되지 않은 입력을 전달한 응답 계약입니다."""

    status: Literal[400]
    code: Annotated[Literal["INVALID_REQUEST"], response_code_schema("INVALID_REQUEST")]
    message: Literal[INVALID_REQUEST]
