"""미구현 기능의 라우트·스키마·테이블 스캐폴딩을 검증합니다."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from smartbudget_server.config import Settings
from smartbudget_server.database import Base
from smartbudget_server.main import create_app
from smartbudget_server.transaction.schemas import TransactionCreate, TransactionUpdate


def _settings(tmp_path: Path) -> Settings:
    """스캐폴딩 OpenAPI 검사에 사용할 독립 설정을 만듭니다."""
    return Settings(
        _env_file=None,
        jwt_secret="x" * 43,
        database_path=tmp_path / "scaffolds.sqlite3",
    )


def test_scaffold_routes_match_target_operations(tmp_path):
    """신규 라우트의 메서드·식별자·응답 상태가 목표 OpenAPI와 일치합니다."""
    target = json.loads(
        (Path(__file__).resolve().parents[1] / "docs/openapi.json").read_text(
            encoding="utf-8"
        )
    )
    live = create_app(_settings(tmp_path)).openapi()

    for path, methods in target["paths"].items():
        if path == "/api/v1/version" or path.startswith("/api/v1/auth/"):
            continue
        assert set(live["paths"][path]) == set(methods)
        for method, expected in methods.items():
            actual = live["paths"][path][method]
            assert actual["operationId"] == expected["operationId"]
            assert actual["summary"] == expected["summary"]
            assert set(actual["responses"]) == set(expected["responses"])
            assert actual["security"] == [{"BearerAuth": []}]

    ocr_body = live["paths"]["/api/v1/proxy/ocr"]["post"]["requestBody"]
    files = ocr_body["content"]["multipart/form-data"]["schema"]["properties"]["files"]
    assert files["minItems"] == 1
    assert files["maxItems"] == 10


def test_scaffold_models_are_registered_before_lifespan():
    """앱 시작의 create_all 전에 신규 영속 모델이 공통 메타데이터에 등록됩니다."""
    assert {"transactions", "monthly_budgets", "reports"} <= set(Base.metadata.tables)


def test_transaction_schema_enforces_category_and_patch_contract():
    """거래 유형별 카테고리와 PATCH의 type·category 동시 입력을 검증합니다."""
    valid = {
        "date": "2026-09-16",
        "type": "expense",
        "source": "manual",
        "category": "food",
        "amount": 1000,
    }
    assert TransactionCreate.model_validate_json(json.dumps(valid)).amount == 1000

    invalid = {**valid, "category": "salary"}
    with pytest.raises(ValidationError):
        TransactionCreate.model_validate_json(json.dumps(invalid))
    with pytest.raises(ValidationError):
        TransactionUpdate.model_validate_json('{"type":"income"}')
