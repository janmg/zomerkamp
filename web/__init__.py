"""Flask web application package for the merged Zomerkamp roster."""

from __future__ import annotations

import os

from flask import Flask

from web.routes import admin_bp, dashboard_bp, import_bp, log_bp


def _apply_migrations() -> None:
    """Add new columns that may not exist in older deployments."""
    from sqlalchemy import text
    from models import Base, get_engine
    engine = get_engine()
    Base.metadata.create_all(engine)

    participant_column_defs = {
        "submitted_at": "VARCHAR(40) NULL",
        "child_first": "VARCHAR(100) NULL",
        "child_last": "VARCHAR(100) NULL",
        "child_att_d1": "TEXT NULL",
        "child_att_d2": "TEXT NULL",
        "child_att_d3": "TEXT NULL",
        "child_att_d4": "TEXT NULL",
        "child_diet": "TEXT NULL",
        "child_notes": "TEXT NULL",
        "first_ntc": "TINYINT(1) NOT NULL DEFAULT 0",
        "sleep_pref": "VARCHAR(120) NULL",
        "sleep_notes": "TEXT NULL",
        "avail_notes": "TEXT NULL",
        "has_car": "TINYINT(1) NOT NULL DEFAULT 0",
        "parent_diet": "TEXT NULL",
        "survey_chat": "VARCHAR(120) NULL",
    }

    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE participants ADD COLUMN messaging "
                "ENUM('whatsapp','signal','telegram','none') NOT NULL DEFAULT 'whatsapp'"
            ))
            conn.commit()
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text(
                "ALTER TABLE participants MODIFY COLUMN messaging "
                "ENUM('whatsapp','signal','telegram','sms','none') NOT NULL DEFAULT 'whatsapp'"
            ))
            conn.commit()
        except Exception:
            pass  # Already has sms
        try:
            conn.execute(text(
                "ALTER TABLE participants ADD COLUMN `group` "
                "VARCHAR(100) NULL DEFAULT NULL"
            ))
            conn.commit()
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text(
                "ALTER TABLE participants MODIFY COLUMN `group` VARCHAR(100) NULL DEFAULT NULL"
            ))
            conn.commit()
        except Exception:
            pass  # Already VARCHAR
        for column_name, sql_type in participant_column_defs.items():
            try:
                conn.execute(text(
                    f"ALTER TABLE participants ADD COLUMN `{column_name}` {sql_type}"
                ))
                conn.commit()
            except Exception:
                pass  # Column already exists


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-zomerkamp-secret")

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(import_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(log_bp)

    _apply_migrations()

    return app