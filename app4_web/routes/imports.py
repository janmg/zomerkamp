"""Import/upload routes (app1 functionality)."""

from __future__ import annotations

import io

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models import get_session
from app4_web.services.import_service import import_participants_from_handle, import_tasks_from_handle

import_bp = Blueprint("imports", __name__)


def _open_uploaded_text(file_storage) -> io.TextIOWrapper:
    return io.TextIOWrapper(file_storage.stream, encoding="utf-8-sig", newline="")


@import_bp.route("/import", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        action = request.form.get("action", "")
        session = get_session()
        try:
            if action == "upload-tasks":
                tasks_file = request.files.get("tasks_csv")
                if tasks_file and tasks_file.filename:
                    with _open_uploaded_text(tasks_file) as handle:
                        summary = import_tasks_from_handle(handle, session)
                    flash(
                        f"Tasks: {summary['imported']} processed, {summary['skipped']} skipped ({summary['added']} added, {summary['updated']} updated).",
                        "success",
                    )
                    for warning in summary["warnings"]:
                        flash(f"Task import warning: {warning}", "warning")
                else:
                    flash("Select a tasks CSV file to upload.", "warning")

            elif action == "upload-participants":
                participants_file = request.files.get("participants_csv")
                if participants_file and participants_file.filename:
                    with _open_uploaded_text(participants_file) as handle:
                        summary = import_participants_from_handle(handle, session)
                    flash(
                        f"Participants: {summary['imported']} processed, {summary['skipped']} skipped ({summary['added']} added, {summary['updated']} updated).",
                        "success",
                    )
                    for warning in summary["warnings"]:
                        flash(f"Participant import warning: {warning}", "warning")
                else:
                    flash("Select a participants CSV file to upload.", "warning")

            else:
                flash("Unknown action.", "error")
        except ValueError as exc:
            flash(str(exc), "error")
        finally:
            session.close()

        return redirect(url_for("imports.upload"))

    return render_template("import.html")
