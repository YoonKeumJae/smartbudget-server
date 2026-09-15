"""파일 SQLite에 계정과 로그인 제한을 저장하고 트랜잭션을 관리합니다."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import (
    JSON,
    URL,
    Boolean,
    CheckConstraint,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    """인증 모델을 함께 초기화하기 위한 SQLAlchemy 메타데이터입니다."""


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


def build_engine(path: Path) -> Engine:
    """파일 DB 연결을 구성하고 새 DB에 인증 테이블을 생성합니다."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path)),
        poolclass=NullPool,
        connect_args={
            "timeout": 5,
            "isolation_level": None,
            "check_same_thread": False,
        },
    )
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def read_session(engine: Engine) -> Iterator[Session]:
    """명시적 읽기 트랜잭션의 연결을 요청 종료 후 반환합니다."""
    with Session(engine, expire_on_commit=False) as session:
        session.connection().exec_driver_sql("BEGIN")
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def write_session(engine: Engine) -> Iterator[Session]:
    """SQLite 쓰기 잠금으로 상태 확인과 변경을 원자적으로 처리합니다."""
    with Session(engine, expire_on_commit=False) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
