"""Configuration for the merged Zomerkamp roster application."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER", "zomerkamp_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "change_me")
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