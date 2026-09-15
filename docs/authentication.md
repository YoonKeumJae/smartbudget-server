# 사용자 관리 및 인증 API

FastAPI, PyJWT, SQLAlchemy와 파일 SQLite로 구현한 v1 계약입니다. 웹과 안드로이드가 같은 JSON API를 사용합니다. 실행 설정은 [server.md](server.md)를 참고합니다. 실행 중 `/docs`와 `/openapi.json`에서 요청·응답 스키마를 확인할 수 있습니다.

## 공통 계약

POST·PUT은 `Content-Type: application/json`을 사용합니다. 알 수 없는 필드, 잘못된 자료형, 쿼리 파라미터, GET 본문은 400입니다. 오류 응답에 입력값·비밀번호·토큰·DB 경로를 포함하지 않습니다. 응답에는 `Cache-Control: no-store`를 설정합니다.

모든 API 응답은 HTTP 상태와 같은 `status`, 영문 `message`, `data`를 포함합니다. 오류의 `data`는 null입니다.

```json
{"status":200,"message":"The request has been accepted and processed.","data":null}
```

| 상태 | message | 의미 |
| --- | --- | --- |
| 200 | The request has been accepted and processed. | 성공 |
| 400 | The request parameters or format are invalid. | 요청 형식·입력 정책 위반 |
| 401 | The username or password is incorrect. | 로그인 실패; 아이디 존재 여부를 구분하지 않음 |
| 401 | Authentication is required or the token is invalid. | 토큰 누락·검증 실패·만료·폐기 |
| 409 | The username is already in use. | 가입 아이디 중복 |
| 429 | Too many sign-in attempts. Please try again later. | 로그인 일시 제한; Retry-After는 남은 초 |
| 503 | The service is temporarily unavailable. | DB 잠금·일시 사용 불가 |

401 응답에는 `WWW-Authenticate: Bearer`를 설정합니다. 위 503은 DB 오류 응답이며 Uvicorn의 동시 요청 제한 응답까지 이 JSON 형식을 보장하지는 않습니다.

## 입력 정책

- 아이디: 4–12자, ASCII 영문·숫자만 허용합니다. 소문자로 저장하여 대소문자를 구분하지 않습니다. 공백을 자동 제거하지 않습니다.
- 비밀번호: 8–20자, `A–Z`, `a–z`, `0–9`, `!@#$%^&*_-+=?`만 허용합니다. 영문·숫자·특수문자 세 종류 중 두 종류 이상이 필요합니다. 대소문자를 구분하며 공백·한글·그 외 문자를 거부합니다. 가입·비밀번호 변경에 이 정책을 적용하며, 로그인은 입력한 비밀번호를 해시와 비교합니다.
- 표시 이름: 일반 공백을 앞뒤에서 제거한 후 2–10자입니다. 한글 음절·자모, ASCII 영문·숫자·일반 공백만 허용합니다. 중간 공백을 유지하고 글자 수에 포함합니다. 공백만 있는 이름·탭·줄바꿈·제어문자·다른 특수문자를 거부합니다. 중복은 허용합니다.
- 월 예산: 초기값 null(미설정), 정수 0–10,000,000원입니다. 문자열·실수·불리언은 거부하며 null로 초기화할 수 있습니다.

## API

### POST /api/v1/auth/sign-up

필수 JSON: `username`, `password`, `display_name`.

```json
{"username":"User123","password":"Password1!","display_name":"홍길동"}
```

성공 200의 data는 null입니다. 입력 오류 400, 아이디 중복 409, DB 오류 503입니다. 가입 성공으로 로그인 토큰을 발급하지 않습니다.

### POST /api/v1/auth/sign-in

필수 JSON: `username`, `password`.

```json
{"username":"user123","password":"Password1!"}
```

성공 200의 data는 `{"token":"<JWT>"}`입니다. 입력 오류 400, 인증 실패 401, 재시도 제한 429, DB 오류 503입니다.

정규화된 아이디별 최근 5분간 10회 실패하면 열 번째 요청부터 3분간 차단합니다. 5분 경계에 도달한 실패는 집계에서 제외합니다. 차단 중에는 올바른 비밀번호도 거부하며 추가 요청이 차단 시간을 연장하지 않습니다. 성공 또는 차단 만료 시 초기화합니다. 존재하지 않는 아이디도 같은 정책과 더미 해시 검증을 사용합니다. 상태를 SQLite에 저장하고 만료된 항목을 로그인 요청 시 정리합니다. 전체 기록 수 제한이나 기록 용량에 따른 거부는 없습니다.

### POST /api/v1/auth/refresh

필수 JSON: `{"token":"<JWT>"}`. Authorization 헤더를 함께 보내거나 헤더로 대체하면 400입니다.

성공 200의 data는 `{"token":"<새 JWT>"}`입니다. token 누락·잘못된 요청 400, 검증 실패·이미 만료된 토큰 401, DB 오류 503입니다.

### GET /api/v1/auth/account

필수 헤더: `Authorization: Bearer <JWT>`. 본문·쿼리로 토큰을 전달하지 않습니다.

성공 200의 data:

```json
{"display_name":"홍길동","budget_limit":null}
```

잘못된 요청 400, 토큰 누락·검증 실패 401, DB 오류 503입니다. JWT의 사용자만 조회하며 다른 사용자 ID를 받지 않습니다.

### PUT /api/v1/auth/account

JSON의 token으로 인증합니다. Authorization 헤더를 함께 보내거나 대체하면 400입니다. 선택 필드는 `password`, `display_name`, `budget_limit`입니다.

```json
{"token":"<JWT>","display_name":"새 이름","budget_limit":10000000}
```

생략한 값은 유지합니다. budget_limit의 null은 초기화이고 password·display_name의 명시적 null은 400입니다. token만 제공하면 변경 없이 200입니다. 하나라도 잘못되면 아무 값도 변경하지 않습니다. 성공 data는 null입니다. 요청 오류 400, token 누락·빈 값·검증 실패 401, DB 오류 503입니다. token의 잘못된 자료형은 400입니다.

현재 비밀번호를 별도로 요구하지 않습니다. 새 비밀번호 해시 저장과 token_version 증가를 한 트랜잭션으로 처리합니다. 해당 사용자의 기존 JWT를 모두 폐기하므로 변경 후 다시 로그인해야 합니다. 다른 사용자의 토큰은 영향받지 않습니다.

## 토큰 수명과 보안

JWT는 HS256으로 서명하며 기본 유효기간은 발급부터 5일입니다. sub(내부 사용자 ID), ver(폐기 버전), jti(고유 ID), iat, exp, iss, aud를 검증합니다. 사용자가 존재하고 활성 상태이며 DB의 버전과 일치해야 합니다. 비밀번호는 Argon2id 해시로 저장합니다.

갱신은 아직 유효한 JWT로 새 발급 시각·고유 ID·유효기간의 JWT를 생성합니다. 갱신 전 토큰도 원래 만료 시각까지 유효합니다. 별도 리프레시 토큰, 30일 누적 갱신 상한, 로그인 세션 테이블은 없습니다. 프론트엔드 권장 조건은 **발급 후 1일 이상 경과 AND 만료까지 6시간 이내**입니다. 서버는 이 권장 시점을 강제하지 않습니다. 만료 후에는 다시 로그인합니다.

클라이언트는 JWT를 안전하게 보관하고 요청 위치 규칙을 따릅니다. 로그아웃 API는 없으며 클라이언트에서 토큰을 삭제해도 서버에서 그 토큰을 폐기하지 않습니다. 웹·안드로이드의 저장·갱신 코드는 이 서버 구현 범위에 포함되지 않습니다. 실제 배포에서는 HTTPS로 평문 비밀번호와 토큰을 보호해야 합니다.

조회·수정은 인증된 본인 계정에만 적용합니다. 거래 CRUD, 이메일 인증, 비밀번호 복구, 전체 활동 기록은 구현 범위에 없습니다.

## 제공 문서에서 확정·보완된 내용

다섯 경로, 성공 상태·봉투·data.token 및 기본 5일 JWT 계약을 유지했습니다. 토큰 전달 위치를 확정했고 로그인 429·Retry-After와 DB 오류 503을 추가했습니다. 입력 규칙, 예산 null 초기화·상한, 수정의 원자성, 비밀번호 변경 시 모든 기존 JWT 폐기, 갱신 전 JWT 유지 및 갱신 권장 조건의 AND 해석을 구체화했습니다.
