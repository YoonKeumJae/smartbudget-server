"""서버 버전 조회와 로컬·Docker 메타데이터 로딩을 검증합니다."""

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from accountbook.config import Settings
from accountbook.main import create_app
from accountbook.version.schemas import BuildChannel, VersionData
from accountbook.version.service import load_version_data

ENDPOINT = "/api/v1/version"
TEST_TIMESTAMP = datetime.fromisoformat("2026-09-23T21:30:00+09:00")
TEST_COMMIT = "a" * 40


def _settings(tmp_path) -> Settings:
    """버전 API 테스트용 독립 DB와 서명 설정을 생성합니다."""
    return Settings(
        _env_file=None,
        jwt_secret="x" * 43,
        database_path=tmp_path / "test.sqlite3",
    )


def test_version_endpoint_returns_injected_build_metadata(tmp_path):
    """GET 응답이 주입된 빌드 일시·커밋·실행 환경을 그대로 반환합니다."""
    version_data = VersionData(
        build_timestamp=TEST_TIMESTAMP,
        version=TEST_COMMIT,
        channel=BuildChannel.REMOTE_REGISTRY,
    )
    with TestClient(create_app(_settings(tmp_path), version_data)) as client:
        response = client.get(ENDPOINT)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": 200,
        "code": "SUCCESS",
        "message": "The request has been accepted and processed.",
        "data": {
            "build_timestamp": "2026-09-23T21:30:00+09:00",
            "version": TEST_COMMIT,
            "channel": "remote_registry",
        },
    }


def test_version_endpoint_rejects_query_and_body(tmp_path):
    """버전 조회에 쿼리나 GET 본문을 전달하면 공통 400 응답을 반환합니다."""
    version_data = VersionData(
        build_timestamp=TEST_TIMESTAMP,
        version=TEST_COMMIT,
        channel=BuildChannel.LOCAL_DIRECT,
    )
    with TestClient(create_app(_settings(tmp_path), version_data)) as client:
        query_response = client.get(ENDPOINT, params={"verbose": "true"})
        body_response = client.request("GET", ENDPOINT, content=b"{}")

    for response in (query_response, body_response):
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"


def test_version_openapi_contract(tmp_path):
    """라이브 OpenAPI가 공개 필드와 무인증·응답 상태 계약을 명시합니다."""
    version_data = VersionData(
        build_timestamp=TEST_TIMESTAMP,
        version=TEST_COMMIT,
        channel=BuildChannel.LOCAL_DOCKER,
    )
    with TestClient(create_app(_settings(tmp_path), version_data)) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"][ENDPOINT]["get"]
    assert operation["security"] == []
    assert set(operation["responses"]) == {"200", "400"}
    data_schema = schema["components"]["schemas"]["VersionData"]
    assert set(data_schema["required"]) == {
        "build_timestamp",
        "version",
        "channel",
    }
    assert data_schema["properties"]["channel"]["$ref"].endswith("/BuildChannel")
    assert schema["components"]["schemas"]["BuildChannel"]["enum"] == [
        "local_direct",
        "local_docker",
        "remote_registry",
    ]


def test_official_openapi_contains_version_contract():
    """공식 목표 OpenAPI가 구현된 버전 API의 필드와 채널 값을 유지합니다."""
    target = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/openapi.json").read_text(
            encoding="utf-8"
        )
    )

    operation = target["paths"][ENDPOINT]["get"]
    assert operation["security"] == []
    assert set(operation["responses"]) == {"200", "400"}
    assert target["components"]["schemas"]["BuildChannel"]["enum"] == [
        "local_direct",
        "local_docker",
        "remote_registry",
    ]
    assert set(target["components"]["schemas"]["VersionData"]["required"]) == {
        "build_timestamp",
        "version",
        "channel",
    }


def test_load_version_data_reads_docker_build_file(tmp_path):
    """Docker 이미지의 빌드 정보 파일을 검증된 공개 스키마로 읽습니다."""
    build_info_path = tmp_path / "build-info.json"
    build_info_path.write_text(
        json.dumps(
            {
                "build_timestamp": "2026-09-23T21:30:00+09:00",
                "version": "sha256:" + "b" * 64,
                "channel": "local_docker",
            }
        ),
        encoding="utf-8",
    )

    result = load_version_data(build_info_path, tmp_path)

    assert result.version == "sha256:" + "b" * 64
    assert result.channel is BuildChannel.LOCAL_DOCKER
    assert result.build_timestamp == TEST_TIMESTAMP


def test_load_version_data_falls_back_to_local_direct(tmp_path):
    """빌드 파일과 Git이 없는 직접 실행은 시각과 unknown 버전을 제공합니다."""
    result = load_version_data(tmp_path / "missing.json", tmp_path)

    assert result.build_timestamp.utcoffset() is not None
    assert result.version == "unknown"
    assert result.channel is BuildChannel.LOCAL_DIRECT
