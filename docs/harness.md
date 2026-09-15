# Codex 완료 전 검증 하네스

![Codex 완료 전 검증 하네스 실행 흐름](harness-flow.svg)

이 프로젝트에서 Codex가 파일을 변경하면 종료 직전에 검증을 실행합니다. 대화만 한 턴은 검증하지 않습니다. 검사 대상은 Git이 관리하거나 관리할 수 있는 프로젝트 파일이며 `.venv/`와 캐시 파일은 제외합니다.

## 작업 전 문서 안내

`UserPromptSubmit` 훅은 매 요청에서 시작 지문을 유지하거나 처음 저장한 뒤, `docs/index.md`를 먼저 읽고 작업 범위에 맞는 문서를 확인하라는 짧은 추가 컨텍스트를 Codex에 전달합니다. 문서 전체를 출력하거나 문서 내용을 별도 상태로 저장하지 않습니다. 이 안내는 실제 읽기 완료를 강제하거나 증명하지 않습니다.

프로젝트 관련 문서는 `docs/` 또는 그 하위 폴더에 두고 새 문서를 추가하거나 문서 목적·읽기 조건이 바뀌면 `docs/index.md`의 표를 갱신합니다. 하위 문서 링크는 index를 기준으로 한 상대 경로를 사용합니다. 매번 모든 문서를 읽는 대신 표에서 해당 작업 조건을 고릅니다. 종료 시 Luna는 index와 관련 문서의 실제 누락·모순·반영 누락을 검토하며, 문서 선택의 증거가 없다는 사실만으로 실패시키지 않습니다.

pytest는 `docs/`와 모든 하위 폴더의 파일 목록을 index 링크와 비교합니다. 새 문서를 표에 등록하지 않거나 존재하지 않는 경로를 남기면 테스트가 실패합니다.

지원 Python 버전은 3.14 계열입니다. 아래 명령을 실행하기 전에 `python3 --version`으로 3.14인지 확인합니다.

## 최초 준비

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

새 Codex 실행에서 프로젝트 훅을 검토하고 신뢰해야 `.codex/hooks.json`이 동작합니다. CLI에서는 `/hooks`로 상태를 확인할 수 있습니다. 훅을 신뢰하기 전에는 검증이 강제되지 않습니다.

## 검증 순서

1. 세션의 첫 요청에서 프로젝트 파일의 내용 지문을 Git에서 제외되는 `.harness-state/`에 저장합니다. 이후에는 마지막으로 검증을 통과한 지문을 유지하며, 실패 후 재개된 요청도 이 지문을 덮어쓰지 않습니다.
2. 종료 직전 마지막 통과 지문과 현재 파일을 비교합니다. Stop 훅 제한은 300초이며, 하네스는 285초 내부 마감 시간을 넘기면 실패로 보고합니다.
3. 변경된 Python 파일에 Ruff의 기본 안전 수정과 포맷팅을 적용한 직후 검사 대상 파일의 지문을 고정합니다.
4. 고정한 지문을 기준으로 Python 컨벤션과 삼중 큰따옴표 docstring 형식(`D300`)을 Ruff로 검사하고, 모든 클래스·함수의 docstring 존재 여부를 추가 검사한 뒤 `pytest -q`를 실행합니다. 테스트가 하나도 수집되지 않으면 pytest가 종료 코드 5를 반환하며, 하네스는 이를 실패로 처리합니다.
5. 앞선 검사가 통과하면 읽기 전용 `gpt-5.6-luna` 실행이 `AGENTS.md`, `docs/`, 변경 코드와 docstring을 검토합니다. 문서 간 모순, 코드 변경의 문서 반영 필요 여부, docstring의 역할·맥락 설명을 판정합니다. 저장 직전에 지문을 다시 만들어 검사 전 지문과 비교하고, 다르면 실패로 보고합니다. 동일하고 모든 검증이 통과했을 때만 고정한 지문을 마지막 통과 지문으로 저장합니다.

Ruff 명령은 각각 최대 15초, pytest는 최대 100초, Luna 검토는 최대 110초 실행합니다. 전체 남은 시간이 더 짧으면 그만큼만 실행합니다. 자동 수정 실패나 시간 초과를 포함한 검증 실패는 통과 지문으로 저장하지 않습니다. 첫 Stop 실패는 Codex에 재개 요청(`decision: "block"`)을 보내고, 재개 후에도 실패하면 `systemMessage` 경고를 반환합니다. **Stop 훅은 종료를 강제로 거부하지 않으므로**, 사용자에게 실패를 실제로 보고하는지는 Codex의 최종 응답에 의존합니다. 검토 실행 자체가 실패해도 통과로 처리하지 않습니다. 이 하네스는 로컬 Codex 실행에 적용되며 GitHub CI는 포함하지 않습니다.

Luna에 전달하는 변경 경로는 `현재 존재`와 `삭제됨`으로 구분합니다. 삭제 파일을 열 수 없다는 사실 자체는 검토 실패 사유가 아닙니다. 추적 파일의 삭제 내용은 필요할 때 작업 트리와 스테이징의 Git diff로 확인합니다. 비추적 파일의 삭제 전 내용은 보관하지 않으며 추측하지 않습니다. 삭제 관련 findings에는 현재 문서·관련 코드·확인 가능한 Git diff에 근거한 문서 모순이나 반영 누락만 포함합니다.

## 수동 확인

```sh
python3 scripts/harness.py verify
```

이 명령은 Ruff, docstring 존재·따옴표 형식, pytest를 확인합니다. Luna 검토는 파일을 변경한 Codex 턴의 종료 훅에서 실행됩니다.

## 실제 Stop 훅 통합 확인

훅 설정이나 삭제 처리 방식을 바꾼 뒤에는 프로젝트 루트에서 실제 Codex 턴 두 개로 생성·삭제 경로를 확인합니다. 먼저 `/hooks`에서 이 프로젝트의 UserPromptSubmit·Stop 훅이 신뢰됨 상태인지 확인합니다. 이 검사는 실제 Luna 호출을 포함하므로 모델 사용량이 발생합니다.

```sh
set -e
test ! -e .harness-e2e-smoke.md
mkdir -p .harness-state
test ! -e .harness-state/e2e-create.jsonl
test ! -e .harness-state/e2e-delete.jsonl
codex exec --ephemeral --json -C "$PWD" -m gpt-5.6-luna -s workspace-write \
  'Create only .harness-e2e-smoke.md with exactly "harness end-to-end smoke test" and a trailing newline. Then finish.' \
  > .harness-state/e2e-create.jsonl
codex exec --ephemeral --json -C "$PWD" -m gpt-5.6-luna -s workspace-write \
  'Delete only .harness-e2e-smoke.md. Then finish.' \
  > .harness-state/e2e-delete.jsonl
```

두 턴의 정상 종료와 통과 지문을 확인합니다. 생성 턴의 지문에는 임시 파일이 포함되어야 하고, 삭제 턴의 지문은 현재 프로젝트 파일과 일치해야 합니다. 아래 확인이 모두 통과할 때만 테스트 로그와 세션 상태를 지웁니다. 실패하면 로그와 상태를 보존하고 원인을 확인합니다.

```sh
python3 - <<'PY'
import hashlib
import json
import runpy
from pathlib import Path

harness = runpy.run_path("scripts/harness.py")
state_path = harness["state_path"]
snapshot = harness["project_snapshot"]
root = harness["ROOT"]
logs = [Path(".harness-state/e2e-create.jsonl"), Path(".harness-state/e2e-delete.jsonl")]
states = []
for log in logs:
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert events[0]["type"] == "thread.started", log
    assert events[-1]["type"] == "turn.completed", log
    state = state_path(events[0]["thread_id"])
    states.append((state, json.loads(state.read_text())))

smoke = ".harness-e2e-smoke.md"
expected = hashlib.sha256(b"harness end-to-end smoke test\n").hexdigest()
assert states[0][1].get(smoke) == expected
assert smoke not in states[1][1]
assert states[1][1] == snapshot(root)
assert not (root / smoke).exists()
for path in [*logs, *(state for state, _ in states)]:
    path.unlink()
print("실제 Stop 훅 생성·삭제 검증 통과")
PY
```
