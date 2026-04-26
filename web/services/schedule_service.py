"""Scheduling operations shared by web and CLI interfaces."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
    _EEST = ZoneInfo("Europe/Helsinki")
except Exception:
    _EEST = timezone(timedelta(hours=3))  # UTC+3 fallback (Helsinki summer time)

from models import Assignment, Participant, Task
from roster_logic import compute_total_points, eligible_candidates


def clear_assignments(session) -> None:
    session.query(Assignment).delete()
    session.commit()


def ensure_single_lead(session, task: Task) -> None:
    active_assignments = [assignment for assignment in task.assignments if assignment.role in {"lead", "helper"}]
    if not active_assignments:
        return
    leads = [assignment for assignment in active_assignments if assignment.role == "lead"]
    if leads:
        return
    active_assignments.sort(key=lambda assignment: (assignment.created_at or datetime.min, assignment.id))
    active_assignments[0].role = "lead"


def remove_backup_assignments_for_task(session, task: Task) -> None:
    for assignment in list(task.assignments):
        if assignment.role == "backup":
            session.delete(assignment)
    session.flush()


def run_schedule(session, keep_existing: bool = False) -> list[str]:
    messages: list[str] = []
    if not keep_existing:
        clear_assignments(session)
        messages.append("Existing assignments were cleared.")

    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()
    participants = session.query(Participant).all()
    if not tasks:
        return ["No tasks found in the database."]
    if not participants:
        return ["No participants found in the database."]

    messages.append(f"Scheduling {len(tasks)} task(s) across {len(participants)} participant(s).")
    for task in tasks:
        remove_backup_assignments_for_task(session, task)
        active_assignments = [assignment for assignment in task.assignments if assignment.role in {"lead", "helper"}]
        assigned_ids = {assignment.participant_id for assignment in task.assignments}
        open_slots = task.people_required - len(active_assignments)

        if open_slots > 0:
            initial_candidates = eligible_candidates(session, task, excluded_ids=assigned_ids)
            if len(initial_candidates) < open_slots:
                messages.append(
                    f"Task '{task.name}' day {task.day}: only {len(active_assignments) + len(initial_candidates)}/{task.people_required} people available."
                )
            lead_exists = any(assignment.role == "lead" for assignment in active_assignments)
            for _ in range(max(open_slots, 0)):
                candidates = eligible_candidates(session, task, excluded_ids=assigned_ids)
                if not candidates:
                    break
                participant = candidates[0]
                role = "helper" if lead_exists else "lead"
                session.add(
                    Assignment(
                        task_id=task.id,
                        participant_id=participant.id,
                        role=role,
                        points_awarded=task.points,
                    )
                )
                session.flush()
                assigned_ids.add(participant.id)
                lead_exists = True

        remove_backup_assignments_for_task(session, task)
        ensure_single_lead(session, task)
        session.commit()

        refreshed = session.get(Task, task.id)
        lead = next((assignment.participant.name for assignment in refreshed.assignments if assignment.role == "lead"), "-")
        helpers = [assignment.participant.name for assignment in refreshed.assignments if assignment.role == "helper"]
        messages.append(f"Task '{refreshed.name}' day {refreshed.day}: lead={lead}, helpers={helpers or '-'}")

    messages.append("Schedule generated successfully.")
    return messages


def refresh_backups(session) -> list[str]:
    messages: list[str] = []
    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()
    for task in tasks:
        remove_backup_assignments_for_task(session, task)
        session.commit()
        messages.append(f"Removed replacement placeholders for '{task.name}' day {task.day}.")
    messages.append("All replacement placeholders removed.")
    return messages


def export_csv(session, output_dir: str) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(_EEST).strftime("%Y%m%d_%H%M%S")
    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()

    schedule_path = output_path / f"schedule_{timestamp}.csv"
    with schedule_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["day", "begin_time", "end_time", "task", "block", "points", "role", "participant", "email"])
        for task in tasks:
            visible_assignments = [item for item in task.assignments if item.role in {"lead", "helper"}]
            for assignment in sorted(visible_assignments, key=lambda item: (item.role, item.participant.name.lower())):
                writer.writerow(
                    [
                        task.day,
                        task.begin_time.strftime("%H:%M"),
                        task.end_time.strftime("%H:%M"),
                        task.name,
                        task.time_block,
                        task.points,
                        assignment.role,
                        assignment.participant.name,
                        assignment.participant.email,
                    ]
                )

    totals = compute_total_points(session)
    participants = sorted(session.query(Participant).all(), key=lambda participant: totals.get(participant.id, 0), reverse=True)
    points_path = output_path / f"points_{timestamp}.csv"
    with points_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "name", "email", "phone", "preference", "points"])
        for rank, participant in enumerate(participants, start=1):
            writer.writerow([rank, participant.name, participant.email, participant.phone or "", participant.preference, totals.get(participant.id, 0)])

    per_person_path = output_path / f"per_person_{timestamp}.csv"
    with per_person_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "email", "phone", "remarks", "day", "begin_time", "end_time", "task", "role", "points_awarded"])
        for participant in sorted(session.query(Participant).all(), key=lambda person: person.name.lower()):
            assignments = sorted(participant.assignments, key=lambda item: (item.task.day, item.task.begin_time, item.task.name))
            if not assignments:
                writer.writerow([participant.name, participant.email, participant.phone or "", participant.remarks or "", "", "", "", "", "", totals.get(participant.id, 0)])
                continue
            for assignment in assignments:
                writer.writerow(
                    [
                        participant.name,
                        participant.email,
                        participant.phone or "",
                        participant.remarks or "",
                        assignment.task.day,
                        assignment.task.begin_time.strftime("%H:%M"),
                        assignment.task.end_time.strftime("%H:%M"),
                        assignment.task.name,
                        assignment.role,
                        assignment.points_awarded,
                    ]
                )

    return {
        "schedule": str(schedule_path),
        "points": str(points_path),
        "per_person": str(per_person_path),
    }


def generate_schedule_csv(session) -> tuple[str, str]:
    timestamp = datetime.now(_EEST).strftime("%Y%m%d_%H%M%S")
    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["day", "begin_time", "end_time", "task", "block", "points", "role", "participant", "email"])
    for task in tasks:
        visible_assignments = [a for a in task.assignments if a.role in {"lead", "helper"}]
        for assignment in sorted(visible_assignments, key=lambda a: (a.role, a.participant.name.lower())):
            writer.writerow([
                task.day, task.begin_time.strftime("%H:%M"), task.end_time.strftime("%H:%M"),
                task.name, task.time_block, task.points,
                assignment.role, assignment.participant.name, assignment.participant.email,
            ])
    return f"schedule_{timestamp}.csv", buf.getvalue()


def generate_points_csv(session) -> tuple[str, str]:
    timestamp = datetime.now(_EEST).strftime("%Y%m%d_%H%M%S")
    totals = compute_total_points(session)
    participants = sorted(session.query(Participant).all(), key=lambda p: totals.get(p.id, 0), reverse=True)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["rank", "name", "email", "phone", "preference", "points"])
    for rank, participant in enumerate(participants, start=1):
        writer.writerow([rank, participant.name, participant.email, participant.phone or "", participant.preference, totals.get(participant.id, 0)])
    return f"points_{timestamp}.csv", buf.getvalue()


def generate_per_person_csv(session) -> tuple[str, str]:
    timestamp = datetime.now(_EEST).strftime("%Y%m%d_%H%M%S")
    totals = compute_total_points(session)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "email", "phone", "remarks", "day", "begin_time", "end_time", "task", "role", "points_awarded"])
    for participant in sorted(session.query(Participant).all(), key=lambda p: p.name.lower()):
        assignments = sorted(participant.assignments, key=lambda a: (a.task.day, a.task.begin_time, a.task.name))
        if not assignments:
            writer.writerow([participant.name, participant.email, participant.phone or "", participant.remarks or "", "", "", "", "", "", totals.get(participant.id, 0)])
            continue
        for assignment in assignments:
            writer.writerow([
                participant.name, participant.email, participant.phone or "", participant.remarks or "",
                assignment.task.day, assignment.task.begin_time.strftime("%H:%M"), assignment.task.end_time.strftime("%H:%M"),
                assignment.task.name, assignment.role, assignment.points_awarded,
            ])
    return f"per_person_{timestamp}.csv", buf.getvalue()
