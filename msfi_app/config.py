"""Application configuration settings."""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "msfi.db"


class Config:
    """Default Flask configuration."""

    SECRET_KEY = "msfi-local-dev-key"
    DATABASE = str(DATABASE_PATH)
