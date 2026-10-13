import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load backend/.env regardless of the current working directory
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

DATABASE_URL = os.getenv("PRISM_DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "PRISM_DATABASE_URL is not configured. "
        "Add it to backend/.env"
    )

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("PRISM_SQL_ECHO", "false").lower()
    in {"1", "true", "yes"},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()