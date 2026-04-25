"""Flask web application package for the merged Zomerkamp roster."""

from __future__ import annotations

import os

from flask import Flask

from app4_web.routes import admin_bp, dashboard_bp, import_bp, operations_bp


def _apply_migrations() -> None:
    """Add new columns that may not exist in older deployments."""
    from sqlalchemy import text
    from models import get_engine
    engine = get_engine()
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


def create_app() -> Flask:
	app = Flask(__name__, template_folder="templates")
	app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-zomerkamp-secret")

	app.register_blueprint(dashboard_bp)
	app.register_blueprint(import_bp)
	app.register_blueprint(operations_bp)
	app.register_blueprint(admin_bp)

	_apply_migrations()

	return app