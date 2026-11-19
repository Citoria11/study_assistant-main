import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://study_user:study_pass@db:5432/study_db",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables on startup."""
    # Import models so they are registered on the metadata before create_all
    from app.database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Add new columns that may not exist in older deployments
    _migrate_add_columns()


def _migrate_add_columns() -> None:
    """Idempotent ALTER TABLE for columns added after initial deploy."""
    migrations = [
        "ALTER TABLE study_notebook ADD COLUMN IF NOT EXISTS daily_goal TEXT",
        "ALTER TABLE study_notebook ADD COLUMN IF NOT EXISTS goal_milestones JSONB",
        "ALTER TABLE study_notebook ADD COLUMN IF NOT EXISTS goal_completed JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_translation VARCHAR(32) NOT NULL DEFAULT 'ASV'",
    ]
    with engine.begin() as conn:
        for stmt in migrations:
            conn.execute(text(stmt))


def get_db():
    """FastAPI dependency – yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
