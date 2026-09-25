# 프로젝트 문서 안내

작업 시작 전에 이 표에서 관련 문서를 고릅니다. 조건에 맞는 문서만 읽고, `docs/` 또는 그 하위 폴더에 문서를 추가하거나 목적·읽기 조건이 바뀌면 이 표를 갱신합니다. 하위 폴더 문서는 `architecture/overview.md`처럼 이 파일을 기준으로 한 상대 경로로 링크합니다.

| 문서 | 제목 | 목적 | 반드시 읽어야 하는 작업 조건 |
| --- | --- | --- | --- |
| [index.md](index.md) | 프로젝트 문서 안내 | 작업 범위에 필요한 문서를 찾는 기준 | 모든 프로젝트 작업 시작 전 |
| [harness.md](harness.md) | Codex 완료 전 검증 하네스 | 시작 안내, 종료 검증, 실행·제약을 설명 | 훅·하네스·검증 절차·문서 안내를 변경하거나 확인할 때 |
| [authentication.md](authentication.md) | 사용자 관리 및 인증 API | v1 인증 계약·입력 정책·JWT 수명·본인 계정 접근과 현재 구현 범위 | 인증·회원가입·계정 정보·사용자별 권한·API 계약을 구현, 변경하거나 검증할 때 |
| [server.md](server.md) | 서버 실행 및 설정 | 환경 변수·로컬 실행·SQLite 운영·소스 구조와 기능 추가 | 서버 실행·의존성·환경 설정·DB·운영 제약·소스 구조를 변경하거나 기능을 추가할 때 |
| [azure-deployment-design.md](azure-deployment-design.md) | Azure 개발 서버 배포 설계 | 승인된 Azure VM 배포 범위·보안·업데이트·운영 결정을 기록 | Azure 배포 구현·검토 시 |
| [harness-flow.svg](harness-flow.svg) | Codex 완료 전 검증 하네스 실행 흐름 | 하네스의 실행 단계를 그림으로 설명 | 하네스 실행 순서나 흐름도를 변경할 때 |
| [openapi.json](openapi.json) | API 구현 목표 OpenAPI 3.1 명세 | 구현해야 할 인증·가계부·소비 분석·OCR API 계약의 단일 기준 | API를 구현·변경·검토하거나 클라이언트 계약을 확인할 때 |
| [ocr.md](ocr.md) | 영수증 OCR API 설계 및 구현 결정사항 | OpenAPI의 OCR 계약을 보충하고 구현 시 측정·결정할 처리 방식 기록 | OCR 요청 제한·병렬 처리·비동기 전환·외부 OCR 연동을 구현하거나 검토할 때 |
