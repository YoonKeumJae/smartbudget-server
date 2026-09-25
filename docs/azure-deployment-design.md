# Azure 개발 서버 배포 설계

상태: 2026-09-25 배포 완료. GitHub Actions와 GHCR 설정은 수정하지 않았다.

## 목표와 범위

`develop` 브랜치의 개발 중인 API를 Azure에 배포한다. 도메인을 구매하지 않고 Azure가 제공하는 공인 IP DNS 이름을 사용한다. GHCR은 비공개로 유지하고 GitHub Actions 및 이미지 게시 워크플로는 수정하지 않는다. 배포 결과는 개발 서버이며, API 스텁이 남아 있으므로 완성된 서비스나 실사용 데이터용 프로덕션 환경으로 안내하지 않는다.

## 승인된 기본 구성

- 지역: Korea Central
- VM 아키텍처: x86_64
- OS: Ubuntu LTS
- 최소 사양: Standard_B1ms, 1 vCPU·2 GiB 메모리.
- 네트워크: Azure 관리 공인 IP와 Azure DNS 이름 `smartbudget-dev-kc-260925.koreacentral.cloudapp.azure.com`.
- 웹 접속: HTTPS를 제공하며 외부에는 웹 포트만 연다. SSH는 현재 관리자 공인 IP로 제한한다.
- 데이터: SQLite 파일은 컨테이너 밖의 영속 디스크 경로에 둔다. `.env`와 JWT 서명 키는 저장소·이미지에 포함하지 않는다.
- 컨테이너 이미지: VM에서 `develop` checkout의 Dockerfile로 직접 빌드한다. GHCR의 `latest` 이미지를 pull하지 않는다.

## 구현 원칙

1. VM은 `develop` 브랜치를 checkout하고 앱 서비스만 `docker compose up -d --build --pull never --no-deps smartbudget-server`로 빌드·실행한다. Compose의 `--build`는 checkout한 코드로 이미지를 만들고 `--pull never`는 GHCR의 `latest`를 받지 않게 한다.
2. `develop` 업데이트도 VM에서 `git pull --ff-only origin develop` 후 같은 Compose 명령을 수동 실행한다. GitHub Actions와 자동 배포는 범위 밖이다.
3. Compose 전체를 올리지 않아 Watchtower 서비스를 실행하지 않는다. Watchtower 저장소는 2025-12-17에 읽기 전용 보관 상태가 되었으며, 이 수동 배포 경로에서는 자동 이미지 감지가 필요하지 않다.
4. SQLite와 `.env`는 권한을 제한한다. 백업은 현재 설정하지 않았으며 실제 가계부 데이터를 받기 전에 별도 위치에 복구 가능한 백업이 필요하다.
5. TLS 종료는 Azure가 제공한 DNS 이름을 대상으로 설정하고 외부 HTTPS 요청으로 인증서를 확인한다.

## 비용 기준

2026-09-25 Azure Retail Prices API 기준 Linux B1ms는 시간당 USD 0.026(월 730시간 기준 USD 18.98), Standard IPv4 정적 공인 IP는 시간당 USD 0.005(월 USD 3.65), 32 GiB Standard SSD E4 LRS는 월 USD 2.40이다. 합계는 약 USD 25.03/월이며, 데이터 송신·세금·백업·구독별 할인을 포함하지 않는다. 실제 구독 청구액은 달라질 수 있다. [Azure Retail Prices API 안내](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)

## 실제 배포 상태

- 생성일: 2026-09-25
- 리소스 그룹: `rg-smartbudget-dev-koreacentral`
- VM: `vm-smartbudget-dev-kc`, Korea Central, `Standard_B1ms`, Ubuntu 24.04 x86_64
- OS 디스크: 32 GiB Standard SSD LRS
- 주소: `https://smartbudget-dev-kc-260925.koreacentral.cloudapp.azure.com`
- 앱 소스: `origin/develop`, 배포 커밋 `35167adadf58c797c79a9dbc0ed5cac6d3e25346`
- NSG: SSH 22는 현재 관리자 IPv4 `/32`만 허용, HTTP 80과 HTTPS 443 허용. 앱 포트 8000의 인터넷 인바운드 규칙은 없다.
- 실행: `smartbudget-server` 서비스만 로컬 빌드하여 실행. Watchtower는 실행하지 않는다.
- Caddy가 HTTPS를 종료하고 앱으로 전달한다. `.env`는 VM에서 생성했고 권한은 `600`, DB 데이터 디렉터리는 컨테이너 UID `10001` 소유로 권한 `700`이다. 비밀값은 저장소에 기록하지 않는다.
- 확인: 컨테이너 health `healthy`; HTTPS `/api/v1/version`, `/openapi.json`, `/docs`가 모두 HTTP 200. HTTP 요청은 HTTPS로 리디렉션된다.
- 루트 주소(`/`)에는 별도 페이지나 라우트가 없다. 따라서 브라우저에서 `/`에 접속하면 공통 HTTP 오류 처리기가 `{"status":404,"code":"INVALID_REQUEST","message":"The requested operation is not available.","data":null}`를 반환한다. 이는 서버 중단이 아니라 API 서버에 등록되지 않은 경로의 정상적인 404 응답이다. API 문서는 `/docs`, 구현 중인 API 목록은 `/openapi.json`, 배포 버전은 `/api/v1/version`에서 확인한다. 2026-09-25 외부 HTTPS 요청으로 루트 404와 이 세 경로의 HTTP 200을 확인했다.
- SSH: `ssh -i ~/.ssh/smartbudget-dev-azure azureuser@smartbudget-dev-kc-260925.koreacentral.cloudapp.azure.com`

## 남은 운영 항목

- B1ms는 최소 개발 후보이며 CPU 크레딧이 소진되면 성능 제한이 생길 수 있다.
- 월별 예산·거래 CRUD·소비 리포트·OCR API 일부는 현재 구현 스텁이다.
- 자동 백업은 설정하지 않았다. 실제 가계부 데이터를 넣기 전 별도 위치에 복구 가능한 백업을 구성해야 한다.
- `develop`의 이후 변경은 VM에서 `git pull --ff-only origin develop` 후 수동 빌드 명령을 다시 실행해야 한다. GitHub Actions·Watchtower 자동 배포는 사용하지 않는다.
- 실제 사용자 데이터 기준의 부하·보안 검증은 아직 수행되지 않았다.
