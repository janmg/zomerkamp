#!/usr/bin/env python3
"""Generate, display, back up, and export the task schedule."""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime

from tabulate import tabulate

from models import Assignment, Participant, Task, get_session
from roster_logic import compute_total_points, eligible_candidates


def clear_assignments(session):
    session.query(Assignment).delete()
    session.commit()
    print("[INFO] Existing assignments cleared.")


def ensure_single_lead(session, task: Task):
    active_assignments = [assignment for assignment in task.assignments if assignment.role in {"lead", "helper"}]
    if not active_assignments:
        return
    leads = [assignment for assignment in active_assignments if assignment.role == "lead"]
    if leads:
        return
    active_assignments.sort(key=lambda assignment: (assignment.created_at or datetime.min, assignment.id))
    active_assignments[0].role = "lead"


def refresh_backup_for_task(session, task: Task):
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


def run_schedule(session, keep_existing: bool = False):
    if not keep_existing:
        clear_assignments(session)

    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()
    participants = session.query(Participant).all()
    if not tasks:
        print("[WARN] No tasks found in the database.")
        return
    if not participants:
        print("[WARN] No participants found in the database.")
        return

    print(f"Scheduling {len(tasks)} task(s) across {len(participants)} participant(s)...\n")
    for task in tasks:
        active_assignments = [assignment for assignment in task.assignments if assignment.role in {"lead", "helper"}]
        assigned_ids = {assignment.participant_id for assignment in task.assignments}
        open_slots = task.people_required - len(active_assignments)

        if open_slots > 0:
            initial_candidates = eligible_candidates(session, task, excluded_ids=assigned_ids)
            if len(initial_candidates) < open_slots:
                print(
                    f"  [WARN] Task '{task.name}' day {task.day}: only {len(active_assignments) + len(initial_candidates)}/{task.people_required} people available."
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
        print(f"  Task '{refreshed.name}' day {refreshed.day}: lead={lead}, helpers={helpers or '-'}, backup={backup}")

    print("\nSchedule generated successfully.")


def refresh_backups(session):
    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()
    for task in tasks:
        refresh_backup_for_task(session, task)
        session.commit()
        backup = next((assignment.participant.name for assignment in task.assignments if assignment.role == "backup"), None)
        if backup:
            print(f"  Backup for '{task.name}' day {task.day}: {backup}")
        else:
            print(f"  [WARN] No backup available for '{task.name}' day {task.day}.")
    print("\nBackups refreshed.")


def show_schedule(session):
    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()
    if not tasks:
        print("No tasks found.")
        return

    rows = []
    for task in tasks:
        lead = next((assignment.participant.name for assignment in task.assignments if assignment.role == "lead"), "-")
        helpers = ", ".join(assignment.participant.name for assignment in task.assignments if assignment.role == "helper") or "-"
        backup = next((assignment.participant.name for assignment in task.assignments if assignment.role == "backup"), "-")
        rows.append([
            task.day,
            f"{task.begin_time.strftime('%H:%M')}-{task.end_time.strftime('%H:%M')}",
            task.name,
            task.points,
            lead,
            helpers,
            backup,
        ])

    print(tabulate(rows, headers=["Day", "Time", "Task", "Pts", "Lead", "Helpers", "Backup"], tablefmt="rounded_outline"))

    totals = compute_total_points(session)
    leaderboard = sorted(session.query(Participant).all(), key=lambda participant: totals.get(participant.id, 0), reverse=True)
    print("\n--- Points leaderboard ---")
    print(tabulate([[participant.name, participant.email, totals.get(participant.id, 0)] for participant in leaderboard], headers=["Name", "Email", "Points"], tablefmt="simple"))


def export_csv(session, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()

    schedule_path = os.path.join(output_dir, f"schedule_{timestamp}.csv")
    with open(schedule_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["day", "begin_time", "end_time", "task", "block", "points", "role", "participant", "email"])
        for task in tasks:
            for assignment in sorted(task.assignments, key=lambda item: (item.role, item.participant.name.lower())):
                writer.writerow([
                    task.day,
                    task.begin_time.strftime("%H:%M"),
                    task.end_time.strftime("%H:%M"),
                    task.name,
                    task.time_block,
                    task.points,
                    assignment.role,
                    assignment.participant.name,
                    assignment.participant.email,
                ])

    totals = compute_total_points(session)
    participants = sorted(session.query(Participant).all(), key=lambda participant: totals.get(participant.id, 0), reverse=True)
    points_path = os.path.join(output_dir, f"points_{timestamp}.csv")
    with open(points_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "name", "email", "phone", "preference", "points"])
        for rank, participant in enumerate(participants, start=1):
            writer.writerow([rank, participant.name, participant.email, participant.phone or "", participant.preference, totals.get(participant.id, 0)])

    per_person_path = os.path.join(output_dir, f"per_person_{timestamp}.csv")
    with open(per_person_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "email", "phone", "remarks", "day", "begin_time", "end_time", "task", "role", "points_awarded"])
        for participant in sorted(session.query(Participant).all(), key=lambda person: person.name.lower()):
            assignments = sorted(participant.assignments, key=lambda item: (item.task.day, item.task.begin_time, item.task.name))
            if not assignments:
                writer.writerow([participant.name, participant.email, participant.phone or "", participant.remarks or "", "", "", "", "", "", totals.get(participant.id, 0)])
                continue
            for assignment in assignments:
                writer.writerow([
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
                ])

    print(f"  Schedule written to: {schedule_path}")
    print(f"  Points leaderboard written to: {points_path}")
    print(f"  Per-person schedule written to: {per_person_path}")
    print("\nExport complete.")


def build_parser():
    parser = argparse.ArgumentParser(description="Generate and export the task schedule.")
    sub = parser.add_subparsers(dest="command", required=True)

    schedule_parser = sub.add_parser("schedule", help="Run the scheduling algorithm.")
    schedule_parser.add_argument("--keep-existing", action="store_true", dest="keep_existing", help="Preserve existing assignments and fill only missing slots.")
    sub.add_parser("show", help="Display the current schedule.")

    export_parser = sub.add_parser("export", help="Export the schedule to CSV files.")
    export_parser.add_argument("--output", metavar="DIR", default="./exports", help="Directory for CSV output.")

    sub.add_parser("backup", help="Refresh backup assignments for all tasks.")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    session = get_session()
    try:
        if args.command == "schedule":
            run_schedule(session, keep_existing=args.keep_existing)
        elif args.command == "show":
            show_schedule(session)
        elif args.command == "export":
            export_csv(session, args.output)
        elif args.command == "backup":
            refresh_backups(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()