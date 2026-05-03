import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Production: Postgres (Neon, Vercel Postgres, Supabase, etc.)
    # Convert old-style postgres:// to postgresql:// for SQLAlchemy 2.x
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    # Ensure psycopg2 driver
    if DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
else:
    # Local: SQLite file. On serverless (Vercel), copy bundled DB into /tmp for writability.
    IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
    BUNDLED_DB = os.path.join(os.path.dirname(__file__), "..", "data", "factory.db")
    if IS_SERVERLESS:
        import shutil
        DB_PATH = "/tmp/factory.db"
        if not os.path.exists(DB_PATH) and os.path.exists(BUNDLED_DB):
            shutil.copy(BUNDLED_DB, DB_PATH)
    else:
        DB_PATH = os.environ.get("FACTORY_DB", BUNDLED_DB)
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    engine = create_engine(
        f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
