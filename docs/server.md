# 서버 실행 및 설정

Python 3.14를 사용합니다. 구현해야 할 전체 API 계약은 [openapi.json](openapi.json)을 기준으로 합니다. 인증 세부 설명은 [authentication.md](authentication.md), 개발 검증은 [harness.md](harness.md)를 참고합니다.

## 로컬 실행

프로젝트 루트에서 실행합니다.

```sh
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

생성한 키를 로컬 `.env`의 JWT_SECRET에 넣은 다음 실행합니다. 런타임만 설치할 때는 requirements.txt를 사용합니다.

```sh
.venv/bin/python -m accountbook
```

기본 주소는 `http://127.0.0.1:8000`입니다. 실행 중 서버의 `/docs`와 `/openapi.json`은 현재 구현 상태를 보여주며, `docs/openapi.json`은 구현해야 할 목표 계약입니다. 설정 오류는 시작을 중단하며 임시 서명키로 실행하지 않습니다.

## 환경 설정

우선순위는 **시스템 환경 변수 > 실행 디렉터리의 .env > 기본값**입니다. DB 상대 경로는 설정을 읽는 작업 디렉터리 기준의 절대 경로로 고정합니다. 사용하지 않는 .env 항목은 무시합니다.

| 변수 | 기본값 | 규칙 |
| --- | --- | --- |
| JWT_SECRET | 없음, 필수 | 최소 43자; secrets.token_urlsafe(32)로 무작위 생성 |
| JWT_ISSUER | accountbook | 비어 있지 않은 발급자 |
| JWT_AUDIENCE | accountbook-api | 비어 있지 않은 수신 대상 |
| TOKEN_SECONDS | 432000 | 양의 정수 초; 기본 5일 |
| DATABASE_PATH | ./data/accountbook.sqlite3 | SQLite 파일 경로 |
| HOST | 127.0.0.1 | 비어 있지 않은 바인딩 주소 |
| PORT | 8000 | 1–65535 정수 |
| WEB_ORIGINS | [] | 정확한 HTTP/HTTPS origin의 JSON 배열 |

웹 예: `WEB_ORIGINS=["http://localhost:3000","https://example.com"]`. 경로·쿼리·사용자 정보·와일드카드는 허용하지 않습니다. CORS는 GET·POST·PUT, Authorization·Content-Type을 허용하고 Retry-After를 노출합니다. 쿠키 인증을 사용하지 않습니다. CORS는 브라우저 정책이며 안드로이드 인증을 대체하지 않습니다.

`.env`, DB·저널 파일은 Git에서 제외합니다. `.env.example`만 공유합니다. 키·비밀번호·토큰을 로그에 남기지 않습니다. 서명키를 바꾸면 기존 토큰은 검증에 실패합니다. 발급자·수신 대상 변경도 기존 토큰 검증에 영향을 줍니다.

## SQLite와 처리량

시작 시 DB 상위 폴더와 users·login_attempts 테이블을 생성합니다. 기존 테이블 구조를 변경하는 마이그레이션 기능은 없습니다. 스키마 변경 시 별도 이전 절차가 필요합니다.

NullPool로 요청 후 DB 연결을 반환합니다. 쓰기는 BEGIN IMMEDIATE로 직렬화하여 로그인 실패 집계·비밀번호 변경·토큰 발급의 경합을 막습니다. 잠금 대기는 최대 5초이며 요청 중 DB 잠금·사용 불가 오류는 503으로 반환합니다. 시작 시 DB를 열거나 테이블을 생성하지 못하면 서버 시작이 실패합니다.

공식 실행 진입점은 Uvicorn 단일 worker, 동시 처리 제한 16, 접근 로그 비활성화입니다. Argon2 해시·검증은 프로세스당 한 번에 하나만 실행하여 피크 메모리를 줄입니다. SQLite 쓰기 잠금 중 로그인 해시 검증도 수행하므로 인증 쓰기 처리량은 직렬 처리 속도에 제한됩니다. 높은 처리량이 필요해질 때 DB·잠금 전략을 재검토합니다. 만료된 로그인 제한 기록은 다음 로그인에서 정리하며 전역 기록 개수 제한은 없습니다.

Uvicorn 자체의 동시 처리 제한 503은 인증 API의 JSON 봉투와 다를 수 있습니다. 별도의 HTTPS 프록시·배포·자동 백업 인프라는 포함하지 않습니다. 배포 시 HTTPS와 DB·.env 접근 권한을 설정하고, 서버를 완전히 중지한 상태에서 DB 파일을 복사해 백업합니다. 복원·업데이트 전에도 서버를 중지합니다.

## 검증

```sh
.venv/bin/python -m pip check
python3 scripts/harness.py verify
```

수동 verify는 Ruff·docstring·pytest 검사입니다. 별도 Luna 검토와 지문 확인은 [종료 훅 절차](harness.md)에 따릅니다. 테스트는 임시 DB·테스트용 키를 사용하며 실제 사용자 데이터를 요구하지 않습니다.

## 소스 구조와 기능 추가

```text
accountbook/
├── __main__.py       # 서버 실행
├── main.py           # 앱 조립·라우터 등록·DB 수명주기
├── config.py         # 환경 설정
├── database.py       # 공통 Base·DB 연결·트랜잭션
├── http.py           # 공통 응답·오류 처리·OpenAPI
└── auth/
    ├── __init__.py
    ├── router.py     # 인증 API·토큰 전달 규칙·인증 오류 처리
    ├── schemas.py    # 인증 요청·응답 모델
    ├── service.py    # 가입·로그인·계정 변경
    ├── security.py   # 비밀번호 검증·해시·JWT
    └── models.py     # User·LoginAttempt 테이블
```

라우트는 Request의 app.state에서 해당 앱의 설정·엔진을 읽습니다. 모듈 전역에 앱별 DB나 설정을 저장하지 않습니다. main.py는 공통 HTTP 처리, 인증 라우터, 가장 바깥의 CORS 순으로 구성합니다. 인증 전송 검사에서 즉시 반환하는 오류에도 CORS가 적용됩니다.

새 기능은 실제로 추가할 때 auth/와 같은 수준의 디렉토리로 묶고 main.py에서 라우터를 등록합니다. 기능별 models.py는 공통 database.Base를 상속합니다. 앱 시작 시 create_all을 실행하기 전에 해당 모델 모듈을 불러와 메타데이터에 등록해야 합니다. 현재는 인증 라우터 → service → models의 import로 등록합니다. build_engine은 연결만 구성하고 테이블 초기화는 앱 수명주기에서 수행합니다. 별도의 repository·추상 인터페이스 계층은 없습니다.
