"""기능별 라우터와 공통 설정을 조립하고 DB 수명주기를 관리합니다."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from accountbook.auth.router import configure_auth
from accountbook.config import Settings
from accountbook.database import Base, build_engine
from accountbook.http import configure_http
from accountbook.version.router import configure_version
from accountbook.version.schemas import VersionData
from accountbook.version.service import load_version_data


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

    app = FastAPI(title="AccountBook API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.version_data = version_data

    configure_http(app)
    configure_version(app)
    configure_auth(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Retry-After"],
    )

    return app
