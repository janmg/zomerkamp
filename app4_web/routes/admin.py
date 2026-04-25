"""Administrative operation routes (app3 functionality)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import get_session
from app4_web.services import admin_service

admin_bp = Blueprint("admin", __name__)


def _to_int(value: str | None, field_name: str) -> int:
    if not value:
        raise ValueError(f"{field_name} is required.")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a number.") from exc


@admin_bp.route("/admin", methods=["GET", "POST"])
def admin_panel():
    session = get_session()
    try:
        if request.method == "POST":
            action = request.form.get("action", "")
            try:
                if action == "set-unavailable":
                    person = (request.form.get("person") or "").strip()
                    reason = (request.form.get("reason") or "").strip() or None
                    mode = request.form.get("scope") or ""
                    raw_value = (request.form.get("scope_value") or "").strip()
                    value = int(raw_value) if raw_value else None
                    message = admin_service.set_unavailable(session, person, reason, mode=mode, value=value)
                    flash(message, "success")
                elif action == "remove-unavailable":
                    record_id = _to_int(request.form.get("record_id"), "Unavailability id")
                    flash(admin_service.remove_unavailable(session, record_id), "success")
                elif action == "confirm-backup":
                    task_id = _to_int(request.form.get("task_id"), "Task id")
                    flash(admin_service.confirm_backup(session, task_id), "success")
                elif action == "set-lead":
                    task_id = _to_int(request.form.get("task_id"), "Task id")
                    person = (request.form.get("person") or "").strip()
                    flash(admin_service.set_lead(session, task_id, person), "success")
                elif action == "remove-assignment":
                    task_id = _to_int(request.form.get("task_id"), "Task id")
                    person = (request.form.get("person") or "").strip()
                    flash(admin_service.remove_assignment(session, task_id, person), "success")
                elif action == "new-backup":
                    task_id = _to_int(request.form.get("task_id"), "Task id")
                    flash(admin_service.refresh_backup(session, task_id), "success")
                else:
                    flash("Unsupported admin action.", "error")
            except ValueError as exc:
                flash(str(exc), "error")
            return redirect(url_for("admin.admin_panel"))

        people = admin_service.list_people(session)
        day_filter_raw = (request.args.get("day") or "").strip()
        try:
            day_filter = int(day_filter_raw) if day_filter_raw else None
        except ValueError:
            day_filter = None
            flash("Day filter must be numeric.", "warning")
        tasks = admin_service.list_tasks(session, day=day_filter)
        unavailabilities = admin_service.list_unavailable(session)
    finally:
        session.close()

    return render_template(
        "admin.html",
        people=people,
        tasks=tasks,
        unavailabilities=unavailabilities,
        day_filter=day_filter,
    )
