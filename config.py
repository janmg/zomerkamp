"""Configuration for the merged Zomerkamp roster application."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _read_secret_file(path: str) -> str | None:
    secret_path = Path(path)
    if not secret_path.is_absolute():
        secret_path = Path(__file__).resolve().parent / secret_path
    if not secret_path.exists():
        return None
    return secret_path.read_text(encoding="utf-8").strip() or None

DB_USER = os.getenv("DB_USER", "zomerkamp_user")
DB_PASSWORD_FILE = os.getenv("DB_PASSWORD_FILE", ".db_password")
DB_PASSWORD = _read_secret_file(DB_PASSWORD_FILE) or os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "10.0.0.5")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "zomerkamp")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)

EVENT_DAYS = 4
TIME_BLOCKS = ["morning", "afternoon", "evening"]

MORNING_END_HOUR = 12
AFTERNOON_END_HOUR = 17

PREFERENCES = [
    "serving snacks",
    "serving food",
    "cleaning after food",
    "cleaning toilets",
    "organize afternoon games",
    "do not care",
]

PUBLIC_URL = os.getenv("PUBLIC_URL", "https://zomerkamp.janmg.com")