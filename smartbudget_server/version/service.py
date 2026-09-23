"""이미지에 기록된 메타데이터 또는 로컬 Git에서 서버 버전을 읽습니다."""

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from smartbudget_server.version.schemas import BuildChannel, VersionData

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_INFO_PATH = PROJECT_ROOT / "build-info.json"
KOREA_TIMEZONE = timezone(timedelta(hours=9))


def _git_commit(project_root: Path) -> str:
    """로컬 직접 실행의 현재 Git 커밋을 읽고 사용할 수 없으면 unknown을 반환합니다."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except OSError, subprocess.TimeoutExpired:
        return "unknown"
    commit = result.stdout.strip().lower()
    if result.returncode == 0 and len(commit) in {40, 64}:
        return commit
    return "unknown"


def load_version_data(
    build_info_path: Path = BUILD_INFO_PATH,
    project_root: Path = PROJECT_ROOT,
) -> VersionData:
    """Docker 빌드 정보를 우선하고 없으면 로컬 직접 실행 정보를 생성합니다."""
    if build_info_path.is_file():
        return VersionData.model_validate_json(
            build_info_path.read_text(encoding="utf-8")
        )
    return VersionData(
        build_timestamp=datetime.now(KOREA_TIMEZONE),
        version=_git_commit(project_root),
        channel=BuildChannel.LOCAL_DIRECT,
    )
