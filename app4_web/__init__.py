"""Flask web application package for the merged Zomerkamp roster."""

from __future__ import annotations

import os

from flask import Flask

from app4_web.routes import admin_bp, dashboard_bp, import_bp, operations_bp


def create_app() -> Flask:
	app = Flask(__name__, template_folder="templates")
	app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-zomerkamp-secret")

	app.register_blueprint(dashboard_bp)
	app.register_blueprint(import_bp)
	app.register_blueprint(operations_bp)
	app.register_blueprint(admin_bp)

	return app