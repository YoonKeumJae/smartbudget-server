"""인증 API 테스트에 공통으로 사용할 독립 애플리케이션을 제공합니다."""

import pytest
from fastapi.testclient import TestClient

from accountbook.config import Settings
from accountbook.main import create_app


@pytest.fixture
def client(tmp_path):
    """독립 파일 DB와 비밀 없는 테스트 설정을 제공합니다."""
    settings = Settings(
        _env_file=None,
        jwt_secret="x" * 43,
        database_path=tmp_path / "test.sqlite3",
        web_origins=["https://web.example.test"],
    )
    with TestClient(
        create_app(settings), base_url="https://api.example.test"
    ) as result:
        yield result
