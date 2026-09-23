"""환경 변수와 로컬 dotenv에서 서버 설정을 읽고 검증합니다."""

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """API와 실행 진입점이 공유하는 검증된 서버 설정입니다."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    jwt_secret: SecretStr
    jwt_issuer: str = Field(default="smartbudget-server", min_length=1)
    jwt_audience: str = Field(default="smartbudget-server-api", min_length=1)
    token_seconds: int = Field(default=432000, gt=0)
    database_path: Path = Path("./data/smartbudget.sqlite3")
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    web_origins: list[str] = Field(default_factory=list)

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        """JWT 서명에 사용할 필수 비밀키의 최소 길이를 확인합니다."""
        if len(value.get_secret_value()) < 43:
            raise ValueError("JWT secret must contain at least 43 characters")
        return value

    @field_validator("database_path")
    @classmethod
    def resolve_database_path(cls, value: Path) -> Path:
        """작업 디렉터리 변경에도 같은 SQLite 파일을 사용하게 경로를 고정합니다."""
        return value.expanduser().resolve()

    @field_validator("web_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        """CORS에는 경로·자격 증명·와일드카드 없는 HTTP origin만 허용합니다."""
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or "*" in value
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or any(character.isspace() for character in value)
            ):
                raise ValueError("Invalid web origin")
            try:
                parsed.port
            except ValueError:
                raise ValueError("Invalid web origin") from None
        return values
