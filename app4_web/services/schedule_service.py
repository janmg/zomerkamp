"""Scheduling operations shared by web and CLI interfaces."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

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


def refresh_backup_for_task(session, task: Task) -> None:
    for assignment in list(task.assignments):
        if assignment.role == "backup":
            session.delete(assignment)
    session.flush()

    assigned_ids = {assignment.participant_id for assignment in task.assignments if assignment.role in {"lead", "helper"}}
    candidates = eligible_candidates(session, task, excluded_ids=assigned_ids)
    if candidates:
        session.add(
            Assignment(
                task_id=task.id,
                participant_id=candidates[0].id,
                role="backup",
                points_awarded=0,
            )
        )


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

        ensure_single_lead(session, task)
        refresh_backup_for_task(session, task)
        session.commit()

        refreshed = session.get(Task, task.id)
        lead = next((assignment.participant.name for assignment in refreshed.assignments if assignment.role == "lead"), "-")
        helpers = [assignment.participant.name for assignment in refreshed.assignments if assignment.role == "helper"]
        backup = next((assignment.participant.name for assignment in refreshed.assignments if assignment.role == "backup"), "-")
        messages.append(f"Task '{refreshed.name}' day {refreshed.day}: lead={lead}, helpers={helpers or '-'}, reserve={backup}")

    messages.append("Schedule generated successfully.")
    return messages


def refresh_backups(session) -> list[str]:
    messages: list[str] = []
    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()
    for task in tasks:
        refresh_backup_for_task(session, task)
        session.commit()
        backup = next((assignment.participant.name for assignment in task.assignments if assignment.role == "backup"), None)
        if backup:
            messages.append(f"Reserve for '{task.name}' day {task.day}: {backup}")
        else:
            messages.append(f"No reserve available for '{task.name}' day {task.day}.")
    messages.append("Reserves refreshed.")
    return messages


def export_csv(session, output_dir: str) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()

    schedule_path = output_path / f"schedule_{timestamp}.csv"
    with schedule_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["day", "begin_time", "end_time", "task", "block", "points", "role", "participant", "email"])
        for task in tasks:
            for assignment in sorted(task.assignments, key=lambda item: (item.role, item.participant.name.lower())):
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
