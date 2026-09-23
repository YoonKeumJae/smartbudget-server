"""OpenAPI 거래 계약을 저장하는 SQLAlchemy 모델을 정의합니다."""

from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from smartbudget_server.database import Base


class Transaction(Base):
    """사용자별 수입·지출과 원본 발생 시각 및 변경 시각을 저장합니다."""

    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    time: Mapped[time | None] = mapped_column(Time, nullable=True)
    type: Mapped[str] = mapped_column(String(7))
    source: Mapped[str] = mapped_column(String(14))
    category: Mapped[str] = mapped_column(String(32))
    store_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
