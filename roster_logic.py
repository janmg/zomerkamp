"""Shared scheduling helpers for the merged Zomerkamp application."""

from __future__ import annotations

from collections import defaultdict

from models import Assignment, Participant, Task, Unavailability

TASK_PREFERENCE_MAP = {
    "serving snacks": "serving snacks",
    "serving": "serving food",
    "breakfast": "serving food",
    "lunch": "serving food",
    "dinner": "serving food",
    "food prep": "serving food",
    "cleaning after": "cleaning after food",
    "cleanup": "cleaning after food",
    "toilet": "cleaning toilets",
    "games": "organize afternoon games",
    "activity": "organize afternoon games",
    "workshop": "organize afternoon games",
}


def compute_total_points(session) -> dict[int, int]:
    totals: dict[int, int] = defaultdict(int)
    for assignment in session.query(Assignment).filter(Assignment.role != "backup").all():
        totals[assignment.participant_id] += assignment.points_awarded
    return totals


def task_preferred_by(task: Task, participant: Participant) -> bool:
    if participant.preference == "do not care":
        return True
    task_name = task.name.lower()
    for keyword, preference in TASK_PREFERENCE_MAP.items():
        if keyword in task_name and preference == participant.preference:
            return True
    return False


def participant_is_available(participant: Participant, task: Task) -> bool:
    if participant.excluded_all_days:
        return False
    return participant.get_block_availability(task.day, task.time_block)


def participant_is_excluded(session, participant_id: int, task: Task) -> bool:
    for record in session.query(Unavailability).filter_by(participant_id=participant_id).all():
        if record.all_days:
            return True
        if record.day == task.day and record.task_id is None:
            return True
        if record.task_id == task.id:
            return True
    return False


def _minutes(value) -> int:
    return value.hour * 60 + value.minute


def participant_has_conflict(session, participant_id: int, task: Task, exclude_task_id: int | None = None) -> bool:
    assignments = session.query(Assignment).join(Task).filter(Assignment.participant_id == participant_id).all()
    for assignment in assignments:
        other = assignment.task
        if exclude_task_id is not None and other.id == exclude_task_id:
            continue
        if other.day != task.day:
            continue
        starts_before_other_ends = _minutes(task.begin_time) < _minutes(other.end_time)
        other_starts_before_task_ends = _minutes(other.begin_time) < _minutes(task.end_time)
        if starts_before_other_ends and other_starts_before_task_ends:
            return True
    return False


def candidate_score(participant: Participant, task: Task, totals: dict[int, int]) -> tuple[int, int, str]:
    mismatch = 0 if task_preferred_by(task, participant) else 1
    return (mismatch, totals.get(participant.id, 0), participant.name.lower())


def eligible_candidates(session, task: Task, excluded_ids: set[int] | None = None) -> list[Participant]:
    excluded_ids = excluded_ids or set()
    totals = compute_total_points(session)
    candidates = []
    for participant in session.query(Participant).all():
        if participant.id in excluded_ids:
            continue
        if not participant_is_available(participant, task):
            continue
        if participant_is_excluded(session, participant.id, task):
            continue
        if participant_has_conflict(session, participant.id, task, exclude_task_id=task.id):
            continue
        already_assigned = session.query(Assignment).filter_by(task_id=task.id, participant_id=participant.id).first()
        if already_assigned:
            continue
        candidates.append(participant)
    candidates.sort(key=lambda participant: candidate_score(participant, task, totals))
    return candidates