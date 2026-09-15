"""기능별 모델이 공유하는 SQLite 연결과 트랜잭션을 관리합니다."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    """기능별 모델을 함께 초기화하기 위한 SQLAlchemy 메타데이터입니다."""


def build_engine(path: Path) -> Engine:
    """파일 DB 연결을 구성해 앱 수명주기에 전달합니다."""
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
