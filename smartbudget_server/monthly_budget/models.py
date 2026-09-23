"""OpenAPI 월별 예산 계약을 저장하는 SQLAlchemy 모델을 정의합니다."""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from smartbudget_server.database import Base


class MonthlyBudget(Base):
    """사용자와 월 조합별 예산 금액을 한 건만 저장합니다."""

    __tablename__ = "monthly_budgets"
    __table_args__ = (UniqueConstraint("user_id", "month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    month: Mapped[str] = mapped_column(String(7))
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
