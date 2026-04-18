import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/budget.db")


def ensure_db_dir() -> None:
    """Create the database parent directory when using an absolute path.

    Only needed in Docker where DATABASE_URL points to a mounted volume
    (e.g. sqlite:////data/budget.db) that may not exist yet at startup.
    """
    if ":memory:" in DATABASE_URL:
        return
    db_path = DATABASE_URL.replace("sqlite:///", "")
    if not Path(db_path).is_absolute():
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
