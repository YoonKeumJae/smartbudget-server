"""실행 설정의 우선순위와 시작 시 검증을 확인합니다."""

import pytest
from pydantic import ValidationError

from accountbook.config import Settings


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    """환경 변수가 로컬 파일보다 우선하고 경로가 절대 경로로 고정됩니다."""
    env = tmp_path / ".env"
    env.write_text("PORT=8000\nJWT_SECRET=" + "x" * 43 + "\n")
    monkeypatch.setenv("PORT", "9000")
    settings = Settings(_env_file=env)
    assert settings.port == 9000
    assert settings.token_seconds == 432000
    assert settings.database_path.is_absolute()
    assert "x" * 43 not in repr(settings)


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret": "private"},
        {"port": 0},
        {"token_seconds": 0},
        {"jwt_issuer": ""},
        {"web_origins": ["*"]},
        {"web_origins": ["https://web.test/path"]},
        {"web_origins": ["https://user:pass@web.test"]},
    ],
)
def test_invalid_configuration_hides_input(overrides):
    """설정 오류에서 잘못된 기밀 입력값을 출력하지 않습니다."""
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, **({"jwt_secret": "x" * 43} | overrides))
    assert "input_value" not in str(caught.value)
    assert "private" not in str(caught.value)


def test_secret_required(monkeypatch):
    """JWT 비밀키가 없으면 임시 키를 사용하지 않고 시작을 거부합니다."""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
