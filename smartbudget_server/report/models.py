"""OpenAPI 소비 분석 계약을 저장하는 SQLAlchemy 모델을 정의합니다."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from smartbudget_server.database import Base


class Report(Base):
    """사용자별 분석 기간과 LLM이 생성한 전체 리포트를 저장합니다."""

    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    period_type: Mapped[str] = mapped_column(String(7))
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date)
    full_report: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    processing_time_ms: Mapped[int] = mapped_column(Integer)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
