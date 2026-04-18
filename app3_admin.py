#!/usr/bin/env python3
"""Administrative management for the merged Zomerkamp roster."""

from __future__ import annotations

import argparse
import sys

from tabulate import tabulate

from app2_schedule import ensure_single_lead, refresh_backup_for_task
from models import Assignment, Participant, Task, Unavailability, get_session
from roster_logic import compute_total_points


def find_participant(session, name: str) -> Participant | None:
    wanted = name.strip().lower()
    for participant in session.query(Participant).all():
        if wanted in participant.name.lower():
            return participant
    return None


def find_task(session, task_id: int) -> Task | None:
    return session.get(Task, task_id)


def cmd_list_people(session, _args):
    totals = compute_total_points(session)
    participants = sorted(session.query(Participant).all(), key=lambda participant: totals.get(participant.id, 0), reverse=True)
    rows = []
    for participant in participants:
        rows.append([
            participant.id,
            participant.name,
            participant.email,
            participant.phone or "-",
            participant.preference,
            totals.get(participant.id, 0),
            participant.remarks or "-",
            "YES" if participant.excluded_all_days else "no",
        ])
    print(tabulate(rows, headers=["ID", "Name", "Email", "Phone", "Preference", "Points", "Remarks", "Excluded"], tablefmt="rounded_outline"))


def cmd_list_tasks(session, args):
    query = session.query(Task).order_by(Task.day, Task.begin_time, Task.name)
    if args.day:
        query = query.filter_by(day=args.day)
    tasks = query.all()
    rows = []
    for task in tasks:
        lead = next((assignment.participant.name for assignment in task.assignments if assignment.role == "lead"), "-")
        helpers = ", ".join(assignment.participant.name for assignment in task.assignments if assignment.role == "helper") or "-"
        backup = next((assignment.participant.name for assignment in task.assignments if assignment.role == "backup"), "-")
        rows.append([
            task.id,
            task.day,
            f"{task.begin_time.strftime('%H:%M')}-{task.end_time.strftime('%H:%M')}",
            task.name,
            task.time_block,
            task.points,
            task.people_required,
            lead,
            helpers,
            backup,
        ])
    print(tabulate(rows, headers=["TID", "Day", "Time", "Task", "Block", "Pts", "Req", "Lead", "Helpers", "Backup"], tablefmt="rounded_outline"))


def cmd_list_unavailable(session, _args):
    rows = []
    for record in session.query(Unavailability).order_by(Unavailability.id).all():
        scope = "all days" if record.all_days else (f"day {record.day}" if record.day else "specific task")
        rows.append([record.id, record.participant.name, scope, record.task.name if record.task else "-", record.reason or "-"])
    if not rows:
        print("No unavailability records.")
        return
    print(tabulate(rows, headers=["UID", "Participant", "Scope", "Task", "Reason"], tablefmt="rounded_outline"))


def normalize_tasks(session, tasks: list[Task]):
    for task in tasks:
        ensure_single_lead(session, task)
        refresh_backup_for_task(session, task)
    session.commit()


def cmd_set_unavailable(session, args):
    participant = find_participant(session, args.person)
    if participant is None:
        print(f"[ERROR] Participant not found: {args.person!r}")
        sys.exit(1)

    record = Unavailability(participant_id=participant.id, reason=args.reason or None)
    affected_tasks: list[Task] = []

    if args.all_days:
        participant.excluded_all_days = True
        record.all_days = True
        affected_tasks = [assignment.task for assignment in list(participant.assignments)]
        for assignment in list(participant.assignments):
            session.delete(assignment)
        scope = "all days"
    elif args.day:
        record.day = args.day
        for assignment in list(participant.assignments):
            if assignment.task.day == args.day:
                affected_tasks.append(assignment.task)
                session.delete(assignment)
        scope = f"day {args.day}"
    else:
        task = find_task(session, args.task)
        if task is None:
            print(f"[ERROR] Task id {args.task} not found.")
            sys.exit(1)
        record.task_id = task.id
        affected_tasks = [task]
        for assignment in list(participant.assignments):
            if assignment.task_id == task.id:
                session.delete(assignment)
        scope = f"task '{task.name}' day {task.day}"

    session.add(record)
    session.commit()
    normalize_tasks(session, list({task.id: task for task in affected_tasks}.values()))
    print(f"[OK] {participant.name} marked unavailable for {scope}.")


def cmd_remove_unavailable(session, args):
    record = session.get(Unavailability, args.id)
    if record is None:
        print(f"[ERROR] Unavailability record {args.id} not found.")
        sys.exit(1)
    if record.all_days:
        record.participant.excluded_all_days = False
    participant_name = record.participant.name
    session.delete(record)
    session.commit()
    print(f"[OK] Unavailability record {args.id} removed for {participant_name}.")


def cmd_confirm_backup(session, args):
    task = find_task(session, args.task)
    if task is None:
        print(f"[ERROR] Task id {args.task} not found.")
        sys.exit(1)
    backup = next((assignment for assignment in task.assignments if assignment.role == "backup"), None)
    if backup is None:
        print(f"[WARN] No backup found for task '{task.name}' day {task.day}.")
        return
    backup.role = "helper"
    backup.points_awarded = task.points
    refresh_backup_for_task(session, task)
    session.commit()
    print(f"[OK] {backup.participant.name} promoted from backup to helper on '{task.name}' day {task.day} (+{task.points} points).")


def cmd_set_lead(session, args):
    task = find_task(session, args.task)
    if task is None:
        print(f"[ERROR] Task id {args.task} not found.")
        sys.exit(1)
    participant = find_participant(session, args.person)
    if participant is None:
        print(f"[ERROR] Participant not found: {args.person!r}")
        sys.exit(1)
    target = session.query(Assignment).filter_by(task_id=task.id, participant_id=participant.id).first()
    if target is None:
        print(f"[ERROR] {participant.name} is not assigned to task '{task.name}'.")
        sys.exit(1)
    for assignment in task.assignments:
        if assignment.role == "lead":
            assignment.role = "helper"
    target.role = "lead"
    session.commit()
    print(f"[OK] {participant.name} is now lead for '{task.name}' day {task.day}.")


def cmd_remove_assignment(session, args):
    task = find_task(session, args.task)
    if task is None:
        print(f"[ERROR] Task id {args.task} not found.")
        sys.exit(1)
    participant = find_participant(session, args.person)
    if participant is None:
        print(f"[ERROR] Participant not found: {args.person!r}")
        sys.exit(1)
    assignment = session.query(Assignment).filter_by(task_id=task.id, participant_id=participant.id).first()
    if assignment is None:
        print(f"[ERROR] {participant.name} has no assignment for task '{task.name}'.")
        sys.exit(1)
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
    print(f"[OK] Removed {participant.name} ({removed_role}) from '{task.name}' day {task.day}.")


def build_parser():
    parser = argparse.ArgumentParser(description="Admin management for the task roster.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-people", help="List all participants and their points.")

    list_tasks_parser = sub.add_parser("list-tasks", help="List tasks with assignments.")
    list_tasks_parser.add_argument("--day", type=int, help="Filter by day number.")

    sub.add_parser("list-unavailable", help="Show unavailability records.")

    set_unavailable_parser = sub.add_parser("set-unavailable", help="Mark a participant unavailable.")
    set_unavailable_parser.add_argument("--person", required=True, help="Participant name, partial match allowed.")
    set_unavailable_parser.add_argument("--reason", help="Optional reason.")
    group = set_unavailable_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", type=int, metavar="TASK_ID", help="Specific task ID.")
    group.add_argument("--day", type=int, metavar="DAY", help="Entire day.")
    group.add_argument("--all-days", action="store_true", dest="all_days", help="All days.")

    remove_unavailable_parser = sub.add_parser("remove-unavailable", help="Remove an unavailability record.")
    remove_unavailable_parser.add_argument("--id", type=int, required=True, metavar="UID")

    confirm_backup_parser = sub.add_parser("confirm-backup", help="Promote backup to helper and select a new backup.")
    confirm_backup_parser.add_argument("--task", type=int, required=True, metavar="TASK_ID")

    award_backup_parser = sub.add_parser("award-backup", help="Alias for confirm-backup.")
    award_backup_parser.add_argument("--task", type=int, required=True, metavar="TASK_ID")

    set_lead_parser = sub.add_parser("set-lead", help="Set the lead for a task.")
    set_lead_parser.add_argument("--task", type=int, required=True, metavar="TASK_ID")
    set_lead_parser.add_argument("--person", required=True, help="Participant name, partial match allowed.")

    remove_assignment_parser = sub.add_parser("remove-assignment", help="Remove a person from a task.")
    remove_assignment_parser.add_argument("--task", type=int, required=True, metavar="TASK_ID")
    remove_assignment_parser.add_argument("--person", required=True, help="Participant name, partial match allowed.")

    new_backup_parser = sub.add_parser("new-backup", help="Refresh the backup for one task.")
    new_backup_parser.add_argument("--task", type=int, required=True, metavar="TASK_ID")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    session = get_session()
    try:
        if args.command == "list-people":
            cmd_list_people(session, args)
        elif args.command == "list-tasks":
            cmd_list_tasks(session, args)
        elif args.command == "list-unavailable":
            cmd_list_unavailable(session, args)
        elif args.command == "set-unavailable":
            cmd_set_unavailable(session, args)
        elif args.command == "remove-unavailable":
            cmd_remove_unavailable(session, args)
        elif args.command in {"confirm-backup", "award-backup"}:
            cmd_confirm_backup(session, args)
        elif args.command == "set-lead":
            cmd_set_lead(session, args)
        elif args.command == "remove-assignment":
            cmd_remove_assignment(session, args)
        elif args.command == "new-backup":
            task = find_task(session, args.task)
            if task is None:
                print(f"[ERROR] Task id {args.task} not found.")
                sys.exit(1)
            refresh_backup_for_task(session, task)
            session.commit()
            print(f"[OK] Backup refreshed for '{task.name}' day {task.day}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()