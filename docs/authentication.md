# 사용자 관리 및 인증 API

FastAPI, PyJWT, SQLAlchemy와 파일 SQLite 서버에 적용할 v1 목표 계약입니다. 웹과 안드로이드가 같은 JSON API를 사용합니다. 실행 설정은 [server.md](server.md)를 참고합니다. 현재 서버가 실제로 제공하는 요청·응답 스키마는 실행 중 `/docs`와 `/openapi.json`에서 확인합니다.

전체 API 구현 목표와 계약의 기준은 [openapi.json](openapi.json)입니다. 이 문서는 인증 정책의 세부 설명을 보충하며, 내용이 충돌하면 OpenAPI를 따릅니다.

## 현재 구현과의 차이

2026-09-16 현재 Python 서버는 계정 수정을 `PUT /api/v1/auth/account`와 JSON 본문의 token·budget_limit으로 처리하고, 계정 삭제는 제공하지 않습니다. 공통 응답에도 code가 없으며 로그인·갱신 응답은 token만 반환하고 CORS 허용 메서드는 GET·POST·PUT입니다. 아래의 PATCH·DELETE, Bearer 수정 인증, 현재 비밀번호 확인, 월별 예산 분리, code·토큰 만료 정보 응답 계약을 구현할 때 라우터·스키마·서비스·공통 응답·CORS를 함께 변경해야 합니다. 이 문서를 갱신한 것만으로 서버 동작이 바뀌지는 않습니다.

## 공통 계약

POST·PUT·PATCH는 `Content-Type: application/json`을 사용합니다. 알 수 없는 필드나 잘못된 자료형을 전달하거나 허용되지 않은 쿼리 파라미터 또는 GET·DELETE 본문을 전달하면 오류 코드 400을 반환합니다. 오류 응답에 입력값·비밀번호·토큰·DB 경로를 포함하지 않습니다. 응답에는 `Cache-Control: no-store`를 설정합니다.

모든 API 응답은 HTTP 상태와 같은 `status`, 안정적인 영문 `code`, 영문 `message`, `data`를 포함합니다. 오류의 `data`는 null이며 클라이언트는 message가 아니라 code로 분기합니다.

```json
{"status":200,"code":"SUCCESS","message":"The request has been accepted and processed.","data":null}
```

| 상태 | code | message | 의미 |
| --- | --- | --- | --- |
| 200 | `SUCCESS` | The request has been accepted and processed. | 성공 |
| 400 | `INVALID_REQUEST` | The request parameters or format are invalid. | 요청 형식·입력 정책 위반 |
| 401 | `INVALID_CREDENTIALS` | The username or password is incorrect. | 로그인 실패; 아이디 존재 여부를 구분하지 않음 |
| 401 | `AUTHENTICATION_REQUIRED` | Authentication is required or the token is invalid. | 토큰 누락·검증 실패·만료·폐기 |
| 401 | `CURRENT_PASSWORD_INCORRECT` | The current password is incorrect. | 비밀번호 변경 시 현재 비밀번호 불일치 |
| 409 | `USERNAME_CONFLICT` | The username is already in use. | 가입 아이디 중복 |
| 429 | `SIGN_IN_RATE_LIMITED` | Too many sign-in attempts. Please try again later. | 로그인 일시 제한; Retry-After는 남은 초 |
| 503 | `SERVICE_UNAVAILABLE` | The service is temporarily unavailable. | DB 잠금·일시 사용 불가 |

401 응답에는 `WWW-Authenticate: Bearer`를 설정합니다. 위 503은 DB 오류 응답이며 Uvicorn의 동시 요청 제한 응답까지 이 JSON 형식을 보장하지는 않습니다.

## 입력 정책

- 아이디: 4–12자, ASCII 영문·숫자만 허용합니다. 소문자로 저장하여 대소문자를 구분하지 않습니다. 공백을 자동 제거하지 않습니다.
- 비밀번호: 8–20자, `A–Z`, `a–z`, `0–9`, `!@#$%^&*_-+=?`만 허용합니다. 영문·숫자·특수문자 세 종류 중 두 종류 이상이 필요합니다. 대소문자를 구분하며 공백·한글·그 외 문자를 거부합니다. 가입·비밀번호 변경에 이 정책을 적용하며, 로그인은 최대 128자의 원본 입력을 받아 해시와 비교합니다.
- 표시 이름: 원본 입력은 앞뒤 공백을 포함해 최대 256자이며, 일반 공백을 앞뒤에서 제거한 후 2–10자입니다. 한글 음절·자모, ASCII 영문·숫자·일반 공백만 허용합니다. 중간 공백을 유지하고 글자 수에 포함합니다. 공백만 있는 이름·탭·줄바꿈·제어문자·다른 특수문자를 거부합니다. 중복은 허용합니다.

## API

### POST /api/v1/auth/sign-up

필수 JSON: `username`, `password`, `display_name`.

```json
{"username":"User123","password":"Password1!","display_name":"홍길동"}
```

성공 200의 data는 null입니다. 입력이 잘못되면 오류 코드 400, 아이디가 중복되면 오류 코드 409, DB 오류가 발생하면 오류 코드 503을 반환합니다. 가입 성공으로 로그인 토큰을 발급하지 않습니다.

### POST /api/v1/auth/sign-in

필수 JSON: `username`, `password`.

```json
{"username":"user123","password":"Password1!"}
```

성공 200의 data는 token, expires_at, `token_type:"Bearer"`를 포함합니다. expires_at은 JWT의 exp와 같은 시점을 한국 시간 오프셋이 포함된 일시로 반환합니다. 입력이 잘못되면 오류 코드 400, 인증에 실패하면 오류 코드 401, 재시도 제한에 걸리면 오류 코드 429, DB 오류가 발생하면 오류 코드 503을 반환합니다.

정규화된 아이디별 최근 5분간 10회 실패하면 열 번째 요청부터 3분간 차단합니다. 5분 경계에 도달한 실패는 집계에서 제외합니다. 차단 중에는 올바른 비밀번호도 거부하며 추가 요청이 차단 시간을 연장하지 않습니다. 성공 또는 차단 만료 시 초기화합니다. 존재하지 않는 아이디도 같은 정책과 더미 해시 검증을 사용합니다. 상태를 SQLite에 저장하고 만료된 항목을 로그인 요청 시 정리합니다. 전체 기록 수 제한이나 기록 용량에 따른 거부는 없습니다.

### POST /api/v1/auth/refresh

필수 JSON: `{"token":"<JWT>"}`. Authorization 헤더를 함께 보내거나 헤더로 대체하면 오류 코드 400을 반환합니다.

성공 200의 data는 새 token, expires_at, `token_type:"Bearer"`를 포함합니다. token을 누락하거나 요청이 잘못되면 오류 코드 400, 검증에 실패하거나 이미 만료된 토큰을 전달하면 오류 코드 401, DB 오류가 발생하면 오류 코드 503을 반환합니다.

### GET /api/v1/auth/account

필수 헤더: `Authorization: Bearer <JWT>`. 본문·쿼리로 토큰을 전달하지 않습니다.

성공 200의 data:

```json
{"display_name":"홍길동"}
```

요청이 잘못되면 오류 코드 400, 토큰이 누락되거나 검증에 실패하면 오류 코드 401, DB 오류가 발생하면 오류 코드 503을 반환합니다. JWT의 사용자만 조회하며 다른 사용자 ID를 받지 않습니다.

### PATCH /api/v1/auth/account

`Authorization: Bearer <JWT>` 헤더로 인증합니다. 변경 필드는 `password`, `display_name`이며 하나 이상 전달해야 합니다. password를 바꾸려면 current_password를 함께 전달해야 하며 current_password만 전달할 수 없습니다.

```json
{"display_name":"새 이름"}
```

```json
{"current_password":"Password1!","password":"NewPassword2!"}
```

생략한 값은 유지합니다. 빈 객체, 정의되지 않은 필드, password·display_name·current_password의 null 또는 current_password와 password 중 하나만 전달하면 오류 코드 400을 반환합니다. 현재 비밀번호가 일치하지 않으면 `CURRENT_PASSWORD_INCORRECT` 오류 코드와 HTTP 401을 반환합니다. 하나라도 잘못되면 아무 값도 변경하지 않습니다. 성공하면 변경된 display_name을 data에 반환합니다. 토큰이 누락되거나 검증에 실패하면 오류 코드 401, DB 오류가 발생하면 오류 코드 503을 반환합니다.

현재 비밀번호 검증, 새 비밀번호 해시 저장과 token_version 증가를 한 트랜잭션으로 처리합니다. 해당 사용자의 기존 JWT를 모두 폐기하므로 변경 후 다시 로그인해야 합니다. 다른 사용자의 토큰은 영향받지 않습니다.

### DELETE /api/v1/auth/account

`Authorization: Bearer <JWT>` 헤더로 인증한 본인 계정과 해당 사용자의 거래, 월별 예산, 소비 분석 리포트를 삭제합니다. query와 요청 본문은 허용하지 않습니다. 성공하면 성공 코드 200과 data:null을 반환하며 기존 JWT는 더 이상 사용할 수 없습니다. 인증에 실패하면 오류 코드 401, DB 오류가 발생하면 오류 코드 503을 반환합니다.

## 토큰 수명과 보안

JWT는 HS256으로 서명하며 기본 유효기간은 발급부터 5일입니다. sub(내부 사용자 ID), ver(폐기 버전), jti(고유 ID), iat, exp, iss, aud를 검증합니다. 사용자가 존재하고 활성 상태이며 DB의 버전과 일치해야 합니다. 로그인·갱신 응답의 expires_at은 exp와 같은 시점이고 token_type은 항상 Bearer입니다. 비밀번호는 Argon2id 해시로 저장합니다.

갱신은 아직 유효한 JWT로 새 발급 시각·고유 ID·유효기간의 JWT를 생성합니다. 갱신 전 토큰도 원래 만료 시각까지 유효합니다. 별도 리프레시 토큰, 30일 누적 갱신 상한, 로그인 세션 테이블은 없습니다. 프론트엔드 권장 조건은 **발급 후 1일 이상 경과 AND 만료까지 6시간 이내**입니다. 서버는 이 권장 시점을 강제하지 않습니다. 만료 후에는 다시 로그인합니다.

클라이언트는 JWT를 안전하게 보관하고 요청 위치 규칙을 따릅니다. 로그아웃 API는 없으며 클라이언트에서 토큰을 삭제해도 서버에서 그 토큰을 폐기하지 않습니다. 실제 배포에서는 HTTPS로 평문 비밀번호와 토큰을 보호해야 합니다.

조회·수정은 인증된 본인 계정에만 적용합니다.

## 제공 문서에서 확정·보완된 내용

회원가입·로그인·토큰 갱신·본인 정보 조회·수정·삭제 계약을 정의했습니다. 보호 API는 Bearer 헤더로 인증하고, 토큰 갱신만 JSON 본문으로 갱신할 토큰을 받습니다. 로그인 429·Retry-After와 DB 오류 503을 포함하며, 입력 규칙, 토큰 만료 정보, 수정의 원자성, 현재 비밀번호 확인, 비밀번호 변경 시 모든 기존 JWT 폐기, 갱신 전 JWT 유지 및 갱신 권장 조건의 AND 해석을 구체화했습니다.
