"""Codex 종료 훅에서 변경 파일을 찾고 프로젝트 검증을 실행합니다."""

import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".harness-state"
STOP_BUDGET_SECONDS = 285
RUFF_TIMEOUT_SECONDS = 15
PYTEST_TIMEOUT_SECONDS = 100
LUNA_TIMEOUT_SECONDS = 110


def project_snapshot(root: Path) -> dict[str, str]:
    """Git 파일 지문을 만들어 시작 훅과 종료 훅의 변경 비교에 제공합니다."""
    paths = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout
    snapshot = {}
    for name in set(paths.split(b"\0")) - {b""}:
        relative = os.fsdecode(name)
        path = root / relative
        if path.is_symlink():
            content = os.fsencode(os.readlink(path))
        elif path.is_file():
            content = path.read_bytes()
        else:
            content = b"<deleted>"
        snapshot[relative] = hashlib.sha256(content).hexdigest()
    return snapshot


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """두 project_snapshot 결과를 비교해 종료 검증 대상 파일을 고릅니다."""
    return sorted(
        name
        for name in before.keys() | after.keys()
        if before.get(name) != after.get(name)
    )


def state_path(session_id: str) -> Path:
    """main이 마지막 검증 통과 지문을 보관할 세션별 경로를 만듭니다."""
    digest = hashlib.sha256(session_id.encode()).hexdigest()
    return STATE_DIR / f"{digest}.json"


def run_command(
    command: list[str],
    timeout: float,
    input_text: str | None = None,
    deadline: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """외부 명령을 단계·전체 남은 시간 중 짧은 시간만 실행합니다."""
    if deadline is not None:
        timeout = min(timeout, deadline - time.monotonic())
    if timeout <= 0:
        return subprocess.CompletedProcess(
            command, 1, "", "전체 검증 시간이 초과되었습니다."
        )
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(command, 1, "", str(error))


def missing_docstrings(paths: list[str]) -> list[str]:
    """check_project가 모든 클래스·함수의 docstring 누락을 검사하도록 돕습니다."""
    issues = []
    for relative in paths:
        try:
            tree = ast.parse((ROOT / relative).read_text(), filename=relative)
        except (OSError, SyntaxError) as error:
            issues.append(f"{relative}: 구문 검사 실패: {error}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                if not ast.get_docstring(node):
                    issues.append(
                        f"{relative}:{node.lineno}: {node.name}의 docstring이 없습니다."
                    )
    return issues


def apply_safe_fixes(changed: list[str], deadline: float | None = None) -> list[str]:
    """main이 검증 지문을 잡기 전에 변경된 Python 파일을 안전하게 수정합니다."""
    issues = []
    ruff = ROOT / ".venv" / "bin" / "ruff"
    modified_python = [
        path for path in changed if path.endswith(".py") and (ROOT / path).is_file()
    ]
    if modified_python:
        if not ruff.is_file():
            return [".venv에 Ruff가 없습니다. requirements-dev.txt를 설치하세요."]
        fix = run_command(
            [str(ruff), "check", "--fix", "--no-unsafe-fixes", *modified_python],
            timeout=RUFF_TIMEOUT_SECONDS,
            deadline=deadline,
        )
        if fix.returncode:
            issues.append(f"Ruff 안전 수정 실패:\n{fix.stdout}{fix.stderr}".strip())
        formatted = run_command(
            [str(ruff), "format", *modified_python],
            timeout=RUFF_TIMEOUT_SECONDS,
            deadline=deadline,
        )
        if formatted.returncode:
            issues.append(
                f"Ruff 자동 포맷팅 실패:\n{formatted.stdout}{formatted.stderr}".strip()
            )
    return issues


def check_project(all_paths: list[str], deadline: float | None = None) -> list[str]:
    """apply_safe_fixes 뒤 고정한 파일 상태에 Ruff와 pytest 검사를 실행합니다."""
    issues = []
    ruff = ROOT / ".venv" / "bin" / "ruff"
    pytest = ROOT / ".venv" / "bin" / "pytest"
    if not ruff.is_file() or not pytest.is_file():
        return [".venv에 Ruff와 pytest가 없습니다. requirements-dev.txt를 설치하세요."]

    all_python = [
        path for path in all_paths if path.endswith(".py") and (ROOT / path).is_file()
    ]
    if all_python:
        lint = run_command(
            [str(ruff), "check", *all_python],
            timeout=RUFF_TIMEOUT_SECONDS,
            deadline=deadline,
        )
        format_check = run_command(
            [str(ruff), "format", "--check", *all_python],
            timeout=RUFF_TIMEOUT_SECONDS,
            deadline=deadline,
        )
        issues.extend(missing_docstrings(all_python))
        if lint.returncode:
            issues.append(f"Ruff lint 실패:\n{lint.stdout}{lint.stderr}".strip())
        if format_check.returncode:
            issues.append(
                f"Ruff format 실패:\n{format_check.stdout}{format_check.stderr}".strip()
            )

    tests = run_command(
        [str(pytest), "-q"], timeout=PYTEST_TIMEOUT_SECONDS, deadline=deadline
    )
    if tests.returncode:
        issues.append(f"pytest 실패:\n{tests.stdout}{tests.stderr}".strip())
    return issues


def review_project(
    changed: list[str], turn_id: str, deadline: float | None = None
) -> list[str]:
    """자동 검사가 통과한 변경을 별도 읽기 전용 Luna에게 의미 검토시킵니다."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    output = STATE_DIR / f"{hashlib.sha256(turn_id.encode()).hexdigest()}.review.json"
    output.unlink(missing_ok=True)
    changed_files = {"현재 존재": [], "삭제됨": []}
    for relative in changed:
        path = ROOT / relative
        status = "현재 존재" if path.exists() or path.is_symlink() else "삭제됨"
        changed_files[status].append(relative)
    prompt = (
        "이 프로젝트의 독립 검토자입니다. 파일을 수정하지 마세요. AGENTS.md와 "
        "docs/index.md를 읽고 변경 범위에 해당하는 docs 문서, "
        "현재 존재하는 변경 파일 및 관련 코드를 읽으세요. "
        "'삭제됨' 경로는 현재 파일이 없으므로 열 수 없다는 사실 자체를 실패 사유로 삼지 마세요. "
        "추적 파일의 삭제 내용은 필요할 때 Git diff(작업 트리와 스테이징 변경)로 확인하세요. "
        "비추적 파일의 삭제 전 내용은 알 수 없으므로 추측하지 마세요. "
        "삭제 관련 findings에는 현재 문서·관련 코드·확인 가능한 Git diff에서 근거가 확인되는 "
        "문서 모순이나 반영 누락만 넣으세요. 삭제 전 내용을 확인할 수 없다는 이유만으로 "
        "findings를 만들지 마세요. 다음만 판정하세요: "
        "(1) 관련 문서 사이의 실제 모순, (2) 변경 범위에 맞는 docs 문서가 있는지와 "
        "코드·설정 변경에 필요한 문서 반영 여부, "
        "(3) 변경된 Python 클래스·함수의 docstring이 역할과 다른 코드와의 관계를 충분히 설명하는지. "
        "맥락이 적으면 한 문장도 허용합니다. 문서를 읽었다는 증거가 없다는 이유만으로 실패 처리하지 마세요. "
        "실제 문서 누락·모순·반영 누락처럼 근거가 확인되는 문제만 findings에 파일명과 함께 적으세요. "
        "문제가 없으면 approved=true, findings=[]로 답하세요. 변경 파일: "
        + json.dumps(changed_files, ensure_ascii=False)
    )
    result = run_command(
        [
            "codex",
            "exec",
            "--ephemeral",
            "--disable",
            "hooks",
            "-m",
            "gpt-5.6-luna",
            "-c",
            'model_reasoning_effort="low"',
            "-s",
            "read-only",
            "-C",
            str(ROOT),
            "--output-schema",
            str(ROOT / ".codex" / "review-schema.json"),
            "-o",
            str(output),
            "-",
        ],
        timeout=LUNA_TIMEOUT_SECONDS,
        input_text=prompt,
        deadline=deadline,
    )
    if result.returncode:
        output.unlink(missing_ok=True)
        return [f"Luna 검토 실행 실패:\n{result.stderr}".strip()]
    try:
        verdict = json.loads(output.read_text())
    except OSError, json.JSONDecodeError:
        return ["Luna 검토 결과를 읽을 수 없습니다."]
    finally:
        output.unlink(missing_ok=True)
    if not isinstance(verdict, dict) or not isinstance(verdict.get("findings"), list):
        return ["Luna 검토 결과 형식이 올바르지 않습니다."]
    if verdict.get("approved") is True and verdict["findings"] == []:
        return []
    return [
        "Luna 검토 실패: " + ("; ".join(verdict["findings"]) or "승인되지 않았습니다.")
    ]


def hook_response(issues: list[str], already_continued: bool) -> dict:
    """main의 검증 오류를 Codex에 한 번 전달하고 반복 종료 훅을 막습니다."""
    if not issues:
        return {}
    reason = (
        "검증 실패. 작업 완료라고 주장하지 말고 아래 문제를 사용자에게 보고하세요.\n"
        + "\n".join(issues)
    )
    if already_continued:
        return {"systemMessage": reason}
    return {"decision": "block", "reason": reason}


def main() -> None:
    """수동 검증 또는 Codex 시작 지문 저장과 종료 검사·보고를 조정합니다."""
    event = {}
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "verify":
        issues = check_project(sorted(project_snapshot(ROOT)))
        if issues:
            print("\n".join(issues))
            raise SystemExit(1)
        print("Ruff, docstring 및 pytest 검증 통과")
        return
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("Codex 훅 입력은 JSON 객체여야 합니다.")
        session_id = event.get("session_id")
        turn_id = event.get("turn_id")
        if not session_id or not turn_id:
            raise ValueError("Codex 세션 또는 턴 식별자가 없습니다.")
        path = state_path(session_id)

        if action == "start":
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(json.dumps(project_snapshot(ROOT), ensure_ascii=False))
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": "작업 전에 docs/index.md를 읽고, 작업 범위에 해당하는 문서를 확인하세요.",
                        }
                    },
                    ensure_ascii=False,
                )
            )
            return
        if action != "stop":
            raise ValueError("Usage: harness.py start|stop|verify")
        deadline = time.monotonic() + STOP_BUDGET_SECONDS
        if not path.is_file():
            raise FileNotFoundError("마지막 검증 통과 지문이 없습니다.")

        before = json.loads(path.read_text())
        after = project_snapshot(ROOT)
        changed = changed_paths(before, after)
        if time.monotonic() >= deadline:
            raise TimeoutError("전체 검증 시간이 초과되었습니다.")
        if not changed:
            print("{}")
            return
        issues = apply_safe_fixes(changed, deadline=deadline)
        if not issues:
            candidate = project_snapshot(ROOT)
            if time.monotonic() >= deadline:
                issues.append("전체 검증 시간이 초과되었습니다.")
            else:
                issues.extend(check_project(sorted(candidate), deadline=deadline))
                if not issues:
                    reviewed_paths = changed_paths(before, candidate)
                    issues.extend(
                        review_project(reviewed_paths, turn_id, deadline=deadline)
                    )
        if not issues:
            current = project_snapshot(ROOT)
            if time.monotonic() >= deadline:
                issues.append("전체 검증 시간이 초과되었습니다.")
            elif current != candidate:
                issues.append(
                    "검증 중 프로젝트 파일이 변경되었습니다. 재검증이 필요합니다."
                )
            else:
                path.write_text(json.dumps(candidate, ensure_ascii=False))
        response = hook_response(issues, event.get("stop_hook_active", False))
    except Exception as error:
        already_continued = (
            event.get("stop_hook_active", False) if isinstance(event, dict) else False
        )
        response = hook_response([f"하네스 실행 실패: {error}"], already_continued)
    print(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
