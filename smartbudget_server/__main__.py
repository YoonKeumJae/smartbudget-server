"""검증된 설정으로 단일 프로세스 API 서버를 실행합니다."""

import uvicorn

from smartbudget_server.config import Settings
from smartbudget_server.main import create_app


def main() -> None:
    """앱 수명주기와 설정을 연결하고 요청·해시 동시 처리량을 제한합니다."""
    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        workers=1,
        limit_concurrency=16,
        access_log=False,
    )


if __name__ == "__main__":
    main()
