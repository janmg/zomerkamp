"""Administrative actions shared by web and CLI interfaces."""

from __future__ import annotations

from datetime import datetime

from models import Assignment, ChangeLog, Participant, Task, Unavailability
from roster_logic import compute_total_points, eligible_candidates

from web.services.schedule_service import ensure_single_lead, remove_backup_assignments_for_task

DAY_NAMES = {1: "Wednesday", 2: "Thursday", 3: "Friday", 4: "Saturday"}


def _format_task_scope(task: Task) -> str:
    day_name = DAY_NAMES.get(task.day, f"Day {task.day}")
    return f"'{task.name}' ({day_name} {task.begin_time.strftime('%H:%M')}-{task.end_time.strftime('%H:%M')})"


def _task_state(task: Task) -> dict:
    lead = next((assignment.participant.name for assignment in task.assignments if assignment.role == "lead"), None)
    helpers = sorted(assignment.participant.name for assignment in task.assignments if assignment.role == "helper")
    return {"lead": lead, "helpers": helpers}


def _add_log(
    session,
    message: str,
    category: str = "info",
    participant_id: int | None = None,
    task_id: int | None = None,
) -> None:
    session.add(
        ChangeLog(
            message=message,
            category=category,
            participant_id=participant_id,
            task_id=task_id,
        )
    )


def list_logs(session, limit: int = 400) -> list[dict]:
    query = session.query(ChangeLog).order_by(ChangeLog.created_at.desc(), ChangeLog.id.desc())
    logs = query.limit(limit).all()
    rows = []
    for log in logs:
        rows.append(
            {
                "id": log.id,
                "created": log.created_at or datetime.min,
                "category": log.category,
                "participant": log.participant.name if log.participant else "-",
                "task": _format_task_scope(log.task) if log.task else "-",
                "message": log.message,
            }
        )
    return rows


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
    participants = sorted(
        session.query(Participant).all(),
        key=lambda participant: (totals.get(participant.id, 0), participant.name.lower()),
    )
    return [
        {
            "id": participant.id,
            "name": participant.name,
            "email": participant.email,
            "phone": participant.phone or "-",
            "messaging": participant.messaging or "whatsapp",
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
        rows.append(
            {
                "id": task.id,
                "day": task.day,
                "day_name": DAY_NAMES.get(task.day, f"Day {task.day}"),
                "time": f"{task.begin_time.strftime('%H:%M')}-{task.end_time.strftime('%H:%M')}",
                "name": task.name,
                "block": task.time_block,
                "points": task.points,
                "required": task.people_required,
                "lead": lead,
                "helpers": helpers,
            }
        )
    return rows


def list_unavailable(session) -> list[dict]:
    rows = []
    for record in session.query(Unavailability).order_by(Unavailability.id).all():
        scope = (
            "all days"
            if record.all_days
            else (DAY_NAMES.get(record.day, f"Day {record.day}") if record.day else "specific task")
        )
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
        remove_backup_assignments_for_task(session, task)
        ensure_single_lead(session, task)
    session.commit()


def _fill_open_slots_for_task(session, task: Task) -> list[str]:
    replacements: list[str] = []
    active_assignments = [assignment for assignment in task.assignments if assignment.role in {"lead", "helper"}]
    assigned_ids = {assignment.participant_id for assignment in active_assignments}
    open_slots = max(task.people_required - len(active_assignments), 0)
    lead_exists = any(assignment.role == "lead" for assignment in active_assignments)

    for _ in range(open_slots):
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
        replacements.append(participant.name)

    ensure_single_lead(session, task)
    return replacements


def set_unavailable(
    session,
    person_query: str,
    reason: str | None,
    mode: str,
    value: int | None = None,
    return_details: bool = False,
) -> str | dict:
    participant = find_participant(session, person_query)
    if participant is None:
        raise ValueError(f"Participant not found: {person_query!r}")

    record = Unavailability(participant_id=participant.id, reason=reason or None)
    affected_tasks: list[Task] = []
    removed_assignments: list[tuple[Task, str]] = []

    if mode == "all-days":
        participant.excluded_all_days = True
        record.all_days = True
        affected_tasks = [assignment.task for assignment in list(participant.assignments)]
        for assignment in list(participant.assignments):
            removed_assignments.append((assignment.task, assignment.role))
            session.delete(assignment)
        scope = "all days"
    elif mode == "day":
        if value is None:
            raise ValueError("Day value is required.")
        record.day = value
        for assignment in list(participant.assignments):
            if assignment.task.day == value:
                affected_tasks.append(assignment.task)
                removed_assignments.append((assignment.task, assignment.role))
                session.delete(assignment)
        scope = DAY_NAMES.get(value, f"day {value}")
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
                removed_assignments.append((assignment.task, assignment.role))
                session.delete(assignment)
        scope = _format_task_scope(task)
    else:
        raise ValueError(f"Unsupported unavailability mode: {mode}")

    before_states = {task.id: _task_state(task) for task in {task.id: task for task in affected_tasks}.values()}

    session.add(record)
    unique_tasks = list({task.id: task for task in affected_tasks}.values())
    _normalize_tasks(session, unique_tasks)

    replacements_by_task: dict[int, list[str]] = {}
    for task in unique_tasks:
        replacements_by_task[task.id] = _fill_open_slots_for_task(session, task)

    _add_log(
        session,
        f"{participant.name} was marked unavailable for {scope}." + (f" Reason: {reason}." if reason else ""),
        category="availability",
        participant_id=participant.id,
    )

    for task, removed_role in removed_assignments:
        _add_log(
            session,
            f"Impact: {participant.name} was removed as {removed_role} from {_format_task_scope(task)}.",
            category="impact",
            participant_id=participant.id,
            task_id=task.id,
        )

    task_summaries: list[dict] = []
    for task in unique_tasks:
        before = before_states.get(task.id, {"lead": None, "helpers": []})
        after = _task_state(task)

        if before["lead"] != after["lead"] and after["lead"]:
            _add_log(
                session,
                f"Impact: {after['lead']} became lead for {_format_task_scope(task)} after {participant.name} was marked unavailable.",
                category="impact",
                task_id=task.id,
            )

        for replacement_name in replacements_by_task.get(task.id, []):
            _add_log(
                session,
                f"Impact: {replacement_name} was assigned as replacement for {_format_task_scope(task)} after {participant.name} was marked unavailable.",
                category="impact",
                task_id=task.id,
            )

        active_after = [assignment for assignment in task.assignments if assignment.role in {"lead", "helper"}]
        if len(active_after) < task.people_required:
            _add_log(
                session,
                f"Impact: {_format_task_scope(task)} is short-staffed ({len(active_after)}/{task.people_required}) after {participant.name} was marked unavailable.",
                category="impact",
                task_id=task.id,
            )

        task_summaries.append(
            {
                "task": _format_task_scope(task),
                "replacements": replacements_by_task.get(task.id, []),
                "filled": len(active_after),
                "required": task.people_required,
            }
        )

    session.commit()
    message = f"{participant.name} marked unavailable for {scope}."
    if not return_details:
        return message

    return {
        "message": message,
        "participant": participant.name,
        "scope": scope,
        "tasks": task_summaries,
    }


def remove_unavailable(session, record_id: int) -> str:
    record = session.get(Unavailability, record_id)
    if record is None:
        raise ValueError(f"Unavailability record {record_id} not found.")
    if record.all_days:
        record.participant.excluded_all_days = False
    participant_name = record.participant.name
    participant_id = record.participant.id
    session.delete(record)
    _add_log(
        session,
        f"Unavailability was removed for {participant_name}.",
        category="availability",
        participant_id=participant_id,
    )
    session.commit()
    return f"Unavailability record {record_id} removed for {participant_name}."


def confirm_backup(session, task_id: int) -> str:
    raise ValueError("Precomputed replacements are disabled. Replacements are assigned automatically when someone becomes unavailable.")


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
    previous_lead = next((assignment.participant.name for assignment in task.assignments if assignment.role == "lead"), None)
    for assignment in task.assignments:
        if assignment.role == "lead":
            assignment.role = "helper"
    target.role = "lead"
    _add_log(
        session,
        f"{participant.name} is now lead for {_format_task_scope(task)}.",
        category="assignment",
        participant_id=participant.id,
        task_id=task.id,
    )
    if previous_lead and previous_lead != participant.name:
        _add_log(
            session,
            f"Impact: Lead changed from {previous_lead} to {participant.name} for {_format_task_scope(task)}.",
            category="impact",
            task_id=task.id,
        )
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
    removed_role = assignment.role
    before = _task_state(task)
    session.delete(assignment)
    session.commit()

    if was_lead:
        ensure_single_lead(session, task)

    after = _task_state(task)
    _add_log(
        session,
        f"{participant.name} was removed as {removed_role} from {_format_task_scope(task)}.",
        category="assignment",
        participant_id=participant.id,
        task_id=task.id,
    )
    if before["lead"] != after["lead"] and after["lead"]:
        _add_log(
            session,
            f"Impact: {after['lead']} became lead for {_format_task_scope(task)} after removing {participant.name}.",
            category="impact",
            task_id=task.id,
        )
    session.commit()
    return f"Removed {participant.name} ({removed_role}) from '{task.name}' day {task.day}."


def refresh_backup(session, task_id: int) -> str:
    raise ValueError("Precomputed replacements are disabled. Replacements are assigned automatically when someone becomes unavailable.")
