"""Administrative actions shared by web and CLI interfaces."""

from __future__ import annotations

from datetime import datetime

from models import Assignment, Participant, Task, Unavailability
from roster_logic import compute_total_points

from app4_web.services.schedule_service import ensure_single_lead, refresh_backup_for_task


def find_participant(session, name: str) -> Participant | None:
    wanted = name.strip().lower()
    for participant in session.query(Participant).all():
        if wanted in participant.name.lower():
            return participant
    return None


def find_task(session, task_id: int) -> Task | None:
    return session.get(Task, task_id)


def list_people(session) -> list[dict]:
    totals = compute_total_points(session)
    participants = sorted(session.query(Participant).all(), key=lambda participant: totals.get(participant.id, 0), reverse=True)
    return [
        {
            "id": participant.id,
            "name": participant.name,
            "email": participant.email,
            "phone": participant.phone or "-",
            "messaging": participant.messaging or "none",
            "preference": participant.preference,
            "points": totals.get(participant.id, 0),
            "remarks": participant.remarks or "-",
            "excluded": participant.excluded_all_days,
        }
        for participant in participants
    ]


def list_tasks(session, day: int | None = None) -> list[dict]:
    query = session.query(Task).order_by(Task.day, Task.begin_time, Task.name)
    if day is not None:
        query = query.filter_by(day=day)
    rows = []
    for task in query.all():
        lead = next((assignment.participant.name for assignment in task.assignments if assignment.role == "lead"), "-")
        helpers = ", ".join(assignment.participant.name for assignment in task.assignments if assignment.role == "helper") or "-"
        backup = next((assignment.participant.name for assignment in task.assignments if assignment.role == "backup"), "-")
        rows.append(
            {
                "id": task.id,
                "day": task.day,
                "time": f"{task.begin_time.strftime('%H:%M')}-{task.end_time.strftime('%H:%M')}",
                "name": task.name,
                "block": task.time_block,
                "points": task.points,
                "required": task.people_required,
                "lead": lead,
                "helpers": helpers,
                "backup": backup,
            }
        )
    return rows


def list_unavailable(session) -> list[dict]:
    rows = []
    for record in session.query(Unavailability).order_by(Unavailability.id).all():
        scope = "all days" if record.all_days else (f"day {record.day}" if record.day else "specific task")
        rows.append(
            {
                "id": record.id,
                "participant": record.participant.name,
                "scope": scope,
                "task": record.task.name if record.task else "-",
                "reason": record.reason or "-",
                "created": record.created_at or datetime.min,
            }
        )
    return rows


def _normalize_tasks(session, tasks: list[Task]) -> None:
    for task in tasks:
        ensure_single_lead(session, task)
        refresh_backup_for_task(session, task)
    session.commit()


def set_unavailable(
    session,
    person_query: str,
    reason: str | None,
    mode: str,
    value: int | None = None,
) -> str:
    participant = find_participant(session, person_query)
    if participant is None:
        raise ValueError(f"Participant not found: {person_query!r}")

    record = Unavailability(participant_id=participant.id, reason=reason or None)
    affected_tasks: list[Task] = []

    if mode == "all-days":
        participant.excluded_all_days = True
        record.all_days = True
        affected_tasks = [assignment.task for assignment in list(participant.assignments)]
        for assignment in list(participant.assignments):
            session.delete(assignment)
        scope = "all days"
    elif mode == "day":
        if value is None:
            raise ValueError("Day value is required.")
        record.day = value
        for assignment in list(participant.assignments):
            if assignment.task.day == value:
                affected_tasks.append(assignment.task)
                session.delete(assignment)
        scope = f"day {value}"
    elif mode == "task":
        if value is None:
            raise ValueError("Task id value is required.")
        task = find_task(session, value)
        if task is None:
            raise ValueError(f"Task id {value} not found.")
        record.task_id = task.id
        affected_tasks = [task]
        for assignment in list(participant.assignments):
            if assignment.task_id == task.id:
                session.delete(assignment)
        scope = f"task '{task.name}' day {task.day}"
    else:
        raise ValueError(f"Unsupported unavailability mode: {mode}")

    session.add(record)
    session.commit()
    _normalize_tasks(session, list({task.id: task for task in affected_tasks}.values()))
    return f"{participant.name} marked unavailable for {scope}."


def remove_unavailable(session, record_id: int) -> str:
    record = session.get(Unavailability, record_id)
    if record is None:
        raise ValueError(f"Unavailability record {record_id} not found.")
    if record.all_days:
        record.participant.excluded_all_days = False
    participant_name = record.participant.name
    session.delete(record)
    session.commit()
    return f"Unavailability record {record_id} removed for {participant_name}."


def confirm_backup(session, task_id: int) -> str:
    task = find_task(session, task_id)
    if task is None:
        raise ValueError(f"Task id {task_id} not found.")
    backup = next((assignment for assignment in task.assignments if assignment.role == "backup"), None)
    if backup is None:
        raise ValueError(f"No backup found for task '{task.name}' day {task.day}.")
    backup.role = "helper"
    backup.points_awarded = task.points
    refresh_backup_for_task(session, task)
    session.commit()
    return f"{backup.participant.name} promoted from backup to helper on '{task.name}' day {task.day} (+{task.points} points)."


def set_lead(session, task_id: int, person_query: str) -> str:
    task = find_task(session, task_id)
    if task is None:
        raise ValueError(f"Task id {task_id} not found.")
    participant = find_participant(session, person_query)
    if participant is None:
        raise ValueError(f"Participant not found: {person_query!r}")
    target = session.query(Assignment).filter_by(task_id=task.id, participant_id=participant.id).first()
    if target is None:
        raise ValueError(f"{participant.name} is not assigned to task '{task.name}'.")
    for assignment in task.assignments:
        if assignment.role == "lead":
            assignment.role = "helper"
    target.role = "lead"
    session.commit()
    return f"{participant.name} is now lead for '{task.name}' day {task.day}."


def remove_assignment(session, task_id: int, person_query: str) -> str:
    task = find_task(session, task_id)
    if task is None:
        raise ValueError(f"Task id {task_id} not found.")
    participant = find_participant(session, person_query)
    if participant is None:
        raise ValueError(f"Participant not found: {person_query!r}")
    assignment = session.query(Assignment).filter_by(task_id=task.id, participant_id=participant.id).first()
    if assignment is None:
        raise ValueError(f"{participant.name} has no assignment for task '{task.name}'.")

    was_lead = assignment.role == "lead"
    was_backup = assignment.role == "backup"
    removed_role = assignment.role
    session.delete(assignment)
    session.commit()

    if was_lead:
        ensure_single_lead(session, task)
    if not was_backup:
        refresh_backup_for_task(session, task)
    session.commit()
    return f"Removed {participant.name} ({removed_role}) from '{task.name}' day {task.day}."


def refresh_backup(session, task_id: int) -> str:
    task = find_task(session, task_id)
    if task is None:
        raise ValueError(f"Task id {task_id} not found.")
    refresh_backup_for_task(session, task)
    session.commit()
    return f"Backup refreshed for '{task.name}' day {task.day}."
