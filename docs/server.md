# 서버 실행 및 설정

Python 3.14를 사용합니다. 구현해야 할 전체 API 계약은 [openapi.json](openapi.json)을 기준으로 합니다. 인증 세부 설명은 [authentication.md](authentication.md), 개발 검증은 [harness.md](harness.md)를 참고합니다.

## 사전 준비
본 프로젝트에서는 패키지 정합성을 유지하고, CI 안정성 및 venv 사용성을 유지하기 위해 uv 패키지 매니저를 사용합니다.
시스템에 uv 패키지 매니저가 설치되지 않은 상태라면 터미널에 아래 명령을 입력하여 설치합니다.

### Windows
```sh
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Linux, macOS
```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 로컬 실행

프로젝트 루트에서 다음 명령들을 실행합니다.

```sh
uv python install 3.14
uv sync --frozen
cp .env.example .env
```

`uv sync`는 기본적으로 개발 의존성 그룹까지 설치합니다. 생성한 키를 로컬 `.env`의 JWT_SECRET에 넣은 다음 실행합니다. 운영 환경처럼 런타임 의존성만 설치할 때는 `uv sync --frozen --no-dev`를 사용합니다. `uv.lock`은 재현 가능한 설치를 위해 커밋하며, 의존성을 변경한 뒤에는 `uv lock`으로 갱신합니다.

아래 명령어들 중 하나를 사용하여 최소 43자의 랜덤 문자열을 생성합니다. 그리고 해당 문자열의 `.env` 파일의 `JWT_SECRET` 항목에 붙여넣습니다.

```sh
# Method 1(공통)
uv run --frozen python -c "import secrets; print(secrets.token_urlsafe(32))"

# Method 2(Linux, macOS)
openssl rand -base64 32
```

초기 세팅이 완료되었다면 아래 명령을 입력하여 서버를 실행합니다.

```sh
uv run --frozen python -m smartbudget_server
```

기본 주소는 `http://localhost:8000`입니다. 실행 중 서버의 `/docs`와 `/openapi.json`은 현재 구현 상태를 보여주며, `docs/openapi.json`은 구현해야 할 목표 계약입니다. 설정 오류는 시작을 중단하며 임시 서명키로 실행하지 않습니다.

## Docker 실행 및 자동 업데이트

먼저 `.env.example`을 `.env`로 복사하고 `JWT_SECRET`을 설정합니다. 로컬 소스에서 이미지를 빌드해 실행하려면 다음 명령을 사용합니다.

### Linux, macOS

```sh
BUILD_VERSION=$(git rev-parse HEAD) BUILD_TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ) docker compose up -d --build
```

### Windows PowerShell

```powershell
$env:BUILD_VERSION = git rev-parse HEAD
$env:BUILD_TIMESTAMP = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
docker compose up -d --build
```

API는 지정된 포트로 공개되고 SQLite 파일은 호스트 경로 기준 `./data/smartbudget.sqlite3`에 보존됩니다. `docker compose down`은 이 볼륨을 삭제하지 않으며, 데이터를 함께 삭제하려는 경우에만 `docker compose down --volumes`를 사용합니다.

원격 저장소의 이미지를 기반으로 컨테이너를 실행하려면 다음 명령을 사용합니다.

```sh
docker compose pull
docker compose up -d
```

### Azure 개발 VM에서 develop 소스 직접 실행

Azure 개발 VM은 GHCR 이미지를 pull하지 않고, checkout한 `develop` 소스로 앱 서비스를 빌드합니다. Compose의 앱 서비스만 실행해 Watchtower는 시작하지 않습니다.

```sh
git pull --ff-only origin develop
sudo env BUILD_VERSION="$(git rev-parse HEAD)" BUILD_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)" docker compose up -d --build --pull never --no-deps smartbudget-server
```

코드가 바뀔 때 위 명령을 다시 실행합니다. `--pull never`는 같은 GHCR `latest` 태그를 pull하지 않게 하고, `--no-deps`와 서비스 이름 지정은 Watchtower를 실행하지 않게 합니다. 이 경로는 수동 배포이며 GitHub Actions나 5분 자동 업데이트를 사용하지 않습니다. 전체 `docker compose up -d`는 Watchtower도 시작하므로 이 서버 업데이트에 사용하지 않습니다.

유지보수 및 기타 목적으로 인해 서버를 잠시 다운시켜야 할 경우에는 다음 명령을 사용합니다.

```sh
docker compose down
```

## 서버 버전 API

인증 없이 `GET /api/v1/version`을 호출하면 실행 중인 서버의 빌드 정보를 공통 응답 봉투로 반환합니다. 쿼리 파라미터와 요청 본문은 허용하지 않습니다.

```json
{
  "status": 200,
  "code": "SUCCESS",
  "message": "The request has been accepted and processed.",
  "data": {
    "build_timestamp": "2026-09-23T21:30:00+09:00",
    "version": "18ae094000000000000000000000000000000000",
    "channel": "remote_registry"
  }
}
```

`build_timestamp`는 Docker 이미지 빌드 시각이며, 직접 실행에서는 앱 생성 시각입니다. `version`은 Git 커밋 해시 또는 Docker 이미지 해시를 사용합니다. Git 정보를 읽을 수 없는 직접 실행 또는 빌드 인자를 생략한 로컬 Docker 빌드에서는 `unknown`입니다. 위 로컬 Docker 빌드 명령은 현재 시각과 커밋을 빌드 인자로 전달하며, GHCR 게시 워크플로우는 빌드 시각과 `github.sha`를 자동 전달합니다.

`channel` 값은 다음과 같습니다.

| 값 | 의미 |
| --- | --- |
| `local_direct` | Python으로 로컬 소스를 직접 실행 |
| `local_docker` | 로컬 소스에서 빌드한 Docker 이미지 실행 |
| `remote_registry` | GHCR 게시 워크플로우가 빌드한 원격 저장소 이미지 실행 |

## 환경 설정

우선순위는 **시스템 환경 변수 > 실행 디렉터리의 .env > 기본값**입니다. DB 상대 경로는 설정을 읽는 작업 디렉터리 기준의 절대 경로로 고정합니다. 사용하지 않는 .env 항목은 무시합니다.

| 변수 | 기본값 | 규칙 |
| --- | --- | --- |
| JWT_SECRET | 없음, 필수 | 최소 43자; secrets.token_urlsafe(32)로 무작위 생성 |
| JWT_ISSUER | smartbudget-server | 비어 있지 않은 발급자 |
| JWT_AUDIENCE | smartbudget-server-api | 비어 있지 않은 수신 대상 |
| TOKEN_SECONDS | 432000 | 양의 정수 초; 기본 5일 |
| DATABASE_PATH | ./data/smartbudget.sqlite3 | SQLite 파일 경로 |
| HOST | 127.0.0.1 | 비어 있지 않은 바인딩 주소; 공유 `.env.example`과 컨테이너는 0.0.0.0 사용 |
| PORT | 8000 | 1–65535 정수 |
| WEB_ORIGINS | [] | 정확한 HTTP/HTTPS origin의 JSON 배열 |

웹 예: `WEB_ORIGINS=["http://localhost:3000","https://example.com"]`. 경로·쿼리·사용자 정보·와일드카드는 허용하지 않습니다. CORS는 GET·POST·PUT·PATCH·DELETE, Authorization·Content-Type·Idempotency-Key를 허용하고 Retry-After를 노출합니다. 쿠키 인증을 사용하지 않습니다. CORS는 브라우저 정책이며 안드로이드 인증을 대체하지 않습니다.

`.env`, DB·저널 파일은 Git에서 제외합니다. `.env.example`만 공유합니다. 키·비밀번호·토큰을 로그에 남기지 않습니다. 서명키를 바꾸면 기존 토큰은 검증에 실패합니다. 발급자·수신 대상 변경도 기존 토큰 검증에 영향을 줍니다.

## SQLite와 처리량

시작 시 DB 상위 폴더와 users·login_attempts 테이블을 생성합니다. 기존 테이블 구조를 변경하는 마이그레이션 기능은 없습니다. 스키마 변경 시 별도 이전 절차가 필요합니다.

NullPool로 요청 후 DB 연결을 반환합니다. 쓰기는 BEGIN IMMEDIATE로 직렬화하여 로그인 실패 집계·비밀번호 변경·토큰 발급의 경합을 막습니다. 잠금 대기는 최대 5초이며 요청 중 DB 잠금·사용 불가 오류는 503으로 반환합니다. 시작 시 DB를 열거나 테이블을 생성하지 못하면 서버 시작이 실패합니다.

공식 실행 진입점은 Uvicorn 단일 worker, 동시 처리 제한 16, 접근 로그 비활성화입니다. Argon2 해시·검증은 프로세스당 한 번에 하나만 실행하여 피크 메모리를 줄입니다. SQLite 쓰기 잠금 중 로그인 해시 검증도 수행하므로 인증 쓰기 처리량은 직렬 처리 속도에 제한됩니다. 높은 처리량이 필요해질 때 DB·잠금 전략을 재검토합니다. 만료된 로그인 제한 기록은 다음 로그인에서 정리하며 전역 기록 개수 제한은 없습니다.

Uvicorn 자체의 동시 처리 제한 503은 인증 API의 JSON 봉투와 다를 수 있습니다. 별도의 HTTPS 프록시·배포·자동 백업 인프라는 포함하지 않습니다. 배포 시 HTTPS와 DB·.env 접근 권한을 설정하고, 서버를 완전히 중지한 상태에서 DB 파일을 복사해 백업합니다. 복원·업데이트 전에도 서버를 중지합니다.

## 검증

```sh
uv sync --frozen
uv run --frozen python scripts/harness.py verify
uv run pytest
```

수동 verify는 Ruff·docstring·pytest 검사입니다. 별도 Luna 검토와 지문 확인은 [종료 훅 절차](harness.md)에 따릅니다. 테스트는 임시 DB·테스트용 키를 사용하며 실제 사용자 데이터를 요구하지 않습니다.

## 소스 구조와 기능 추가

```text
smartbudget_server/
├── __main__.py       # 서버 실행
├── main.py           # 앱 조립·라우터 등록·DB 수명주기
├── config.py         # 환경 설정
├── database.py       # 공통 Base·DB 연결·트랜잭션
├── http.py           # 공통 응답·오류 처리·OpenAPI
├── auth/
│   ├── __init__.py
│   ├── router.py     # 인증 API·토큰 전달 규칙·인증 오류 처리
│   ├── schemas.py    # 인증 요청·응답 모델
│   ├── service.py    # 가입·로그인·계정 변경
│   ├── security.py   # 비밀번호 검증·해시·JWT
│   └── models.py     # User·LoginAttempt 테이블
├── monthly_budget/
│   ├── router.py     # 월별 예산 조회·저장 API 스텁
│   ├── schemas.py    # 월별 예산 요청·응답 모델
│   └── models.py     # 사용자별 월 예산 테이블
├── transaction/
│   ├── router.py     # 거래 CRUD API 스텁
│   ├── schemas.py    # 거래 요청·응답 모델
│   └── models.py     # 거래 테이블
├── report/
│   ├── router.py     # 소비 분석 생성·조회·삭제 API 스텁
│   ├── schemas.py    # 소비 분석 요청·응답 모델
│   └── models.py     # 소비 분석 리포트 테이블
├── proxy/
│   ├── router.py     # 영수증 OCR 프록시 API 스텁
│   ├── schemas.py    # 파일별 OCR 응답 모델
│   └── models.py     # 영속 모델을 사용하지 않음을 명시
└── version/
    ├── __init__.py
    ├── router.py     # 서버 버전 조회 API
    ├── schemas.py    # 빌드 정보·응답 모델
    └── service.py    # Docker 빌드 정보 또는 로컬 Git 메타데이터 로딩
```

라우트는 Request의 app.state에서 해당 앱의 설정·엔진·버전 정보를 읽습니다. 모듈 전역에 앱별 DB나 설정을 저장하지 않습니다. main.py는 공통 HTTP 처리, 버전·인증 라우터, 가장 바깥의 CORS 순으로 구성합니다. 인증 전송 검사에서 즉시 반환하는 오류에도 CORS가 적용됩니다.

새 기능은 auth/와 같은 수준의 디렉토리로 묶고 main.py에서 라우터를 등록합니다. 기능별 models.py는 공통 database.Base를 상속하며, 영속 데이터가 없는 OCR은 모델 모듈만 유지합니다. 앱 시작 시 create_all을 실행하기 전에 인증·월별 예산·거래·리포트 모델 모듈을 불러와 메타데이터에 등록합니다. 현재 월별 예산·거래·리포트·OCR 라우트 함수는 OpenAPI 계약에 맞춘 구현 대기 스텁이며 실제 API 로직은 포함하지 않습니다. build_engine은 연결만 구성하고 테이블 초기화는 앱 수명주기에서 수행합니다. 별도의 repository·추상 인터페이스 계층은 없습니다.
