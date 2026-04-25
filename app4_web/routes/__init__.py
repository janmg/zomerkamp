"""Flask route blueprints for the Zomerkamp web UI."""

from app4_web.routes.admin import admin_bp
from app4_web.routes.dashboard import dashboard_bp
from app4_web.routes.imports import import_bp
from app4_web.routes.operations import operations_bp

__all__ = ["admin_bp", "dashboard_bp", "import_bp", "operations_bp"]
