"""Codex 완료 검증 하네스의 변경 감지와 실패 보고를 검사합니다."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HARNESS_PATH = Path(__file__).resolve().parent.parent / "scripts" / "harness.py"
SPEC = importlib.util.spec_from_file_location("harness", HARNESS_PATH)
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def test_document_index_lists_every_document() -> None:
    """docs에 새 문서가 생기면 index 표에도 링크를 요구합니다."""
    docs = HARNESS_PATH.parent.parent / "docs"
    links = set(
        re.findall(r"\]\(([^)]+)\)", (docs / "index.md").read_text(encoding="utf-8"))
    )
    documents = {
        path.relative_to(docs).as_posix() for path in docs.rglob("*") if path.is_file()
    }

    assert links == documents


def test_snapshot_detects_edits_and_deletions(tmp_path: Path) -> None:
    """Git 파일 지문이 수정·삭제된 프로젝트 파일을 놓치지 않는지 확인합니다."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    document = tmp_path / "docs.md"
    document.write_text("처음", encoding="utf-8")
    before = harness.project_snapshot(tmp_path)

    document.write_text("변경", encoding="utf-8")
    assert harness.changed_paths(before, harness.project_snapshot(tmp_path)) == [
        "docs.md"
    ]

    document.unlink()
    assert harness.changed_paths(before, harness.project_snapshot(tmp_path)) == [
        "docs.md"
    ]


def test_failed_verification_requests_one_continuation() -> None:
    """검증 실패 시 한 번만 Codex에게 실패 보고를 요청하는지 확인합니다."""
    first = harness.hook_response(["pytest 실패"], False)
    second = harness.hook_response(["pytest 실패"], True)

    assert first["decision"] == "block"
    assert "pytest 실패" in first["reason"]
    assert "decision" not in second
    assert "pytest 실패" in second["systemMessage"]


def test_private_function_needs_docstring(tmp_path: Path, monkeypatch) -> None:
    """Ruff가 놓칠 수 있는 비공개 함수도 하네스가 검사하는지 확인합니다."""
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    source = tmp_path / "module.py"
    source.write_text("def _private():\n    return 1\n", encoding="utf-8")

    assert harness.missing_docstrings(["module.py"]) == [
        "module.py:1: _private의 docstring이 없습니다."
    ]


def test_failed_stop_keeps_changes_across_continuation(tmp_path: Path) -> None:
    """시작·종료 훅의 실제 명령이 재개 프롬프트 뒤에도 실패 변경을 재검사합니다."""
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for relative in ("scripts/harness.py", "pyproject.toml", "uv.lock", ".gitignore"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HARNESS_PATH.parent.parent / relative, target)
    (root / "tests").mkdir()
    (root / "tests/test_smoke.py").write_text(
        "import os\nfrom pathlib import Path\n\n\n"
        'def test_smoke():\n    """임시 저장소의 pytest 실행을 확인합니다."""\n'
        '    if os.getenv("MUTATE_DURING_PYTEST"):\n'
        '        Path("module.py").write_text(\n'
        '            \'def missing():\\n    """테스트 도중 변경을 확인합니다."""\\n    return 8\\n\',\n'
        '            encoding="utf-8",\n'
        "        )\n"
        "    assert True\n",
        encoding="utf-8",
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    fake_codex = binary / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "if os.getenv('MUTATE_DURING_REVIEW'):\n"
        "    pathlib.Path('module.py').write_text("
        '\'def missing():\\n    """검토 도중 변경을 확인합니다."""\\n    return 9\\n\', encoding=\'utf-8\')\n'
        "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text("
        "json.dumps({'approved': True, 'findings': []}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    env = {
        **os.environ,
        "CODEX_COMMAND": json.dumps([sys.executable, str(fake_codex)]),
    }

    def invoke(action: str, turn_id: str, active: bool = False) -> dict:
        """실제 하네스 프로세스에 Codex 형식의 훅 이벤트를 전달합니다."""
        result = subprocess.run(
            [sys.executable, str(root / "scripts/harness.py"), action],
            input=json.dumps(
                {
                    "session_id": "session-1",
                    "turn_id": turn_id,
                    "stop_hook_active": active,
                }
            ),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            cwd=root,
            env=env,
            check=True,
        )
        return json.loads(result.stdout)

    first_start = invoke("start", "first")
    assert first_start["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "docs/index.md" in first_start["hookSpecificOutput"]["additionalContext"]
    assert "작업 범위" in first_start["hookSpecificOutput"]["additionalContext"]
    state = next((root / ".harness-state").glob("*.json"))
    assert "scripts/harness.py" in json.loads(state.read_text(encoding="utf-8"))
    (root / "module.py").write_text("def missing():\n    return 1\n", encoding="utf-8")
    assert invoke("stop", "first")["decision"] == "block"
    assert "module.py" not in json.loads(state.read_text(encoding="utf-8"))
    assert invoke("start", "continuation") == first_start
    assert "docstring" in invoke("stop", "continuation", True)["systemMessage"]

    (root / "module.py").write_text(
        'def missing():\n    """검증 후 지문 갱신을 확인합니다."""\n    return 1\n',
        encoding="utf-8",
    )
    assert invoke("stop", "continuation", True) == {}
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert "module.py" in saved
    assert invoke("start", "next") == first_start
    assert invoke("stop", "next") == {}

    (root / "module.py").write_text(
        'def missing():\n    """검토 도중 변경을 확인합니다."""\n    return 2\n',
        encoding="utf-8",
    )
    env["MUTATE_DURING_REVIEW"] = "1"
    assert invoke("stop", "next")["decision"] == "block"
    assert json.loads(state.read_text(encoding="utf-8")) == saved
    del env["MUTATE_DURING_REVIEW"]

    assert invoke("start", "pytest-race") == first_start
    (root / "module.py").write_text(
        'def missing():\n    """테스트 도중 변경을 확인합니다."""\n    return 3\n',
        encoding="utf-8",
    )
    env["MUTATE_DURING_PYTEST"] = "1"
    assert invoke("stop", "pytest-race")["decision"] == "block"
    assert json.loads(state.read_text(encoding="utf-8")) == saved


def test_run_command_uses_remaining_deadline() -> None:
    """외부 명령이 단계 제한보다 짧은 전체 남은 시간에 종료되게 합니다."""
    result = harness.run_command(
        [sys.executable, "-c", "import time; time.sleep(1)"],
        timeout=15,
        deadline=time.monotonic() + 0.02,
    )
    assert result.returncode != 0
    assert "timed out" in result.stderr


def test_ruff_auto_fix_failure_is_reported(monkeypatch, tmp_path: Path) -> None:
    """Ruff 자동 수정의 시간 초과도 검증 실패로 사용자에게 전달합니다."""
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    (tmp_path / "module.py").write_text(
        'def done():\n    """역할을 설명합니다."""\n    return 1\n',
        encoding="utf-8",
    )

    def command_result(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        """자동 수정 명령만 시간 초과시키고 나머지 검사는 통과시킵니다."""
        if "--fix" in command:
            return subprocess.CompletedProcess(command, 1, "", "timed out")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(harness, "run_command", command_result)
    issues = harness.apply_safe_fixes(["module.py"])
    assert any(
        "Ruff 안전 수정 실패" in issue and "timed out" in issue for issue in issues
    )


def test_pytest_timeout_is_reported(monkeypatch, tmp_path: Path) -> None:
    """pytest 시간 초과가 성공으로 처리되지 않는지 확인합니다."""
    monkeypatch.setattr(harness, "ROOT", tmp_path)

    def command_result(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        """pytest 명령의 제한 시간 만료만 재현합니다."""
        if "pytest" in command:
            assert kwargs["timeout"] == 100
            return subprocess.CompletedProcess(command, 1, "", "timed out")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(harness, "run_command", command_result)
    assert "timed out" in harness.check_project([])[0]


def test_review_marks_deleted_untracked_path(monkeypatch, tmp_path: Path) -> None:
    """비추적 파일 삭제가 실제 지문 비교를 거쳐 Luna에 삭제됨으로 전달됩니다."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "STATE_DIR", tmp_path / ".harness-state")
    deleted = tmp_path / "deleted.md"
    deleted.write_text("untracked-deletion-fixture-content", encoding="utf-8")
    before = harness.project_snapshot(tmp_path)
    deleted.unlink()
    (tmp_path / "current.md").write_text("현재 내용", encoding="utf-8")
    changed = harness.changed_paths(before, harness.project_snapshot(tmp_path))
    prompts = []

    def capture_review(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        """외부 Luna 호출만 대체해 전달 프롬프트와 정상 응답 처리를 확인합니다."""
        prompts.append(kwargs["input_text"])
        Path(command[command.index("-o") + 1]).write_text(
            json.dumps({"approved": True, "findings": []}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(harness, "run_command", capture_review)
    assert harness.review_project(changed, "deleted-file") == []
    assert json.loads(prompts[0].split("변경 파일: ", 1)[1]) == {
        "현재 존재": ["current.md"],
        "삭제됨": ["deleted.md"],
    }
    assert "docs/index.md" in prompts[0]
    assert "문서를 읽었다는 증거가 없다는 이유만으로 실패 처리하지 마세요" in prompts[0]
    assert "untracked-deletion-fixture-content" not in prompts[0]


def test_luna_timeout_is_reported(monkeypatch, tmp_path: Path) -> None:
    """Luna 검토 시간 초과가 검토 실패로 반환되는지 확인합니다."""
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "STATE_DIR", tmp_path / ".harness-state")

    def command_result(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        """Luna 명령의 제한 시간 만료만 재현합니다."""
        assert kwargs["timeout"] == 110
        return subprocess.CompletedProcess(command, 1, "", "timed out")

    monkeypatch.setattr(harness, "run_command", command_result)
    assert "timed out" in harness.review_project(["docs/harness.md"], "turn-1")[0]


def test_ruff_rejects_single_quoted_docstring(tmp_path: Path) -> None:
    """삼중 작은따옴표 docstring을 프로젝트 Ruff 규칙이 거부합니다."""
    source = tmp_path / "module.py"
    source.write_text(
        "def _private():\n    '''역할을 설명합니다.'''\n    return 1\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            str(HARNESS_PATH.parent.parent / "pyproject.toml"),
            str(source),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert "D300" in result.stdout
