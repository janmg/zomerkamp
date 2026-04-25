"""Scheduling operation routes (app2 functionality)."""

from __future__ import annotations

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for

from models import Participant, Task, get_session
from app4_web.services.schedule_service import (
    export_csv,
    generate_per_person_csv,
    generate_points_csv,
    generate_schedule_csv,
    refresh_backups,
    run_schedule,
)

operations_bp = Blueprint("operations", __name__)


@operations_bp.route("/operations", methods=["GET", "POST"])
def operations():
    session = get_session()
    try:
        if request.method == "POST":
            action = request.form.get("action", "")
            if action == "run-schedule":
                keep_existing = request.form.get("keep_existing") == "on"
                for message in run_schedule(session, keep_existing=keep_existing):
                    flash(message, "info")
            elif action == "refresh-backups":
                for message in refresh_backups(session):
                    flash(message, "info")
            elif action == "export-csv":
                output_dir = request.form.get("output_dir", "./exports").strip() or "./exports"
                paths = export_csv(session, output_dir)
                flash(f"Schedule exported to: {paths['schedule']}", "success")
                flash(f"Points exported to: {paths['points']}", "success")
                flash(f"Per-person exported to: {paths['per_person']}", "success")
            else:
                flash("Unsupported operation.", "error")
            return redirect(url_for("operations.operations"))

        summary = {
            "participants": session.query(Participant).count(),
            "tasks": session.query(Task).count(),
            "assigned": sum(1 for participant in session.query(Participant).all() for _ in participant.assignments),
        }
    finally:
        session.close()

    return render_template("operations.html", summary=summary)


def _csv_response(filename: str, content: str) -> Response:
    response = Response(content, mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@operations_bp.route("/operations/download/schedule")
def download_schedule():
    session = get_session()
    try:
        filename, content = generate_schedule_csv(session)
    finally:
        session.close()
    return _csv_response(filename, content)


@operations_bp.route("/operations/download/points")
def download_points():
    session = get_session()
    try:
        filename, content = generate_points_csv(session)
    finally:
        session.close()
    return _csv_response(filename, content)


@operations_bp.route("/operations/download/per-person")
def download_per_person():
    session = get_session()
    try:
        filename, content = generate_per_person_csv(session)
    finally:
        session.close()
    return _csv_response(filename, content)
