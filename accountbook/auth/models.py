"""인증 기능의 계정·로그인 제한 테이블을 공통 메타데이터에 등록합니다."""

from sqlalchemy import JSON, Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from accountbook.database import Base


class User(Base):
    """고유 로그인 아이디와 본인 정보 및 JWT 폐기 버전을 보관합니다."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("budget_limit IS NULL OR budget_limit BETWEEN 0 AND 10000000"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(12), unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String(10))
    budget_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(Integer)


class LoginAttempt(Base):
    """정규화 아이디별 최근 실패 시각과 일시 차단 상태를 저장합니다."""

    __tablename__ = "login_attempts"
    username: Mapped[str] = mapped_column(String(12), primary_key=True)
    failures: Mapped[list[int]] = mapped_column(JSON, default=list)
    blocked_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
