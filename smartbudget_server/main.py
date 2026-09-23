"""기능별 라우터와 공통 설정을 조립하고 DB 수명주기를 관리합니다."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smartbudget_server.auth.router import configure_auth
from smartbudget_server.config import Settings
from smartbudget_server.database import Base, build_engine
from smartbudget_server.http import configure_http
from smartbudget_server.monthly_budget.router import router as monthly_budget_router
from smartbudget_server.proxy.router import router as proxy_router
from smartbudget_server.report.router import router as report_router
from smartbudget_server.transaction.router import router as transaction_router
from smartbudget_server.version.router import configure_version
from smartbudget_server.version.schemas import VersionData
from smartbudget_server.version.service import load_version_data


def create_app(
    settings: Settings | None = None,
    version_data: VersionData | None = None,
) -> FastAPI:
    """설정과 독립 엔진을 가진 FastAPI 앱의 수명 및 라우트를 구성합니다."""
    settings = settings or Settings()
    version_data = version_data or load_version_data()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """앱 시작에 DB를 초기화하고 종료에 엔진을 반환합니다."""
        app.state.engine = build_engine(settings.database_path)
        try:
            Base.metadata.create_all(app.state.engine)
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(title="smartbudget-server API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.version_data = version_data

    configure_http(app)
    configure_version(app)
    configure_auth(app)
    app.include_router(transaction_router)
    app.include_router(monthly_budget_router)
    app.include_router(report_router)
    app.include_router(proxy_router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["Retry-After"],
    )

    return app
