"""인증 없이 서버 빌드 정보를 조회하는 버전 라우트를 등록합니다."""

from fastapi import APIRouter, FastAPI, Request

from accountbook.http import INVALID_REQUEST, documented_response, respond
from accountbook.version.schemas import (
    VersionInvalidRequestEnvelope,
    VersionSuccessEnvelope,
)

router = APIRouter(prefix="/api/v1", tags=["server"])


@router.get(
    "/version",
    response_model=VersionSuccessEnvelope,
    responses={
        200: documented_response(VersionSuccessEnvelope, "서버 버전 정보 조회 완료."),
        400: documented_response(
            VersionInvalidRequestEnvelope,
            "The request parameters or format are invalid.",
        ),
    },
    openapi_extra={"security": []},
)
async def get_version(request: Request):
    """입력 없이 현재 서버의 빌드 시각·버전·실행 환경을 반환합니다."""
    if request.query_params or await request.body():
        return respond(400, code="INVALID_REQUEST", message=INVALID_REQUEST)
    return respond(
        200,
        request.app.state.version_data.model_dump(mode="json"),
    )


def configure_version(app: FastAPI) -> None:
    """앱에 인증이 필요 없는 서버 버전 라우트를 등록합니다."""
    app.include_router(router)
