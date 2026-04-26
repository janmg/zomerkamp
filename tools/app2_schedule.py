#!/usr/bin/env python3
"""Generate, display, and export the task schedule."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tabulate import tabulate

from web.services.schedule_service import (
    export_csv as export_csv_service,
    run_schedule as run_schedule_service,
)
from models import Participant, Task, get_session
from roster_logic import compute_total_points


def run_schedule(session, keep_existing: bool = False):
    for message in run_schedule_service(session, keep_existing=keep_existing):
        print(message)


def show_schedule(session):
    tasks = session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all()
    if not tasks:
        print("No tasks found.")
        return

    rows = []
    for task in tasks:
        lead = next((assignment.participant.name for assignment in task.assignments if assignment.role == "lead"), "-")
        helpers = ", ".join(assignment.participant.name for assignment in task.assignments if assignment.role == "helper") or "-"
        rows.append([
            task.day,
            f"{task.begin_time.strftime('%H:%M')}-{task.end_time.strftime('%H:%M')}",
            task.name,
            task.points,
            lead,
            helpers,
        ])

    print(tabulate(rows, headers=["Day", "Time", "Task", "Pts", "Lead", "Helpers"], tablefmt="rounded_outline"))

    totals = compute_total_points(session)
    leaderboard = sorted(session.query(Participant).all(), key=lambda participant: totals.get(participant.id, 0), reverse=True)
    print("\n--- Points leaderboard ---")
    print(tabulate([[participant.name, participant.email, totals.get(participant.id, 0)] for participant in leaderboard], headers=["Name", "Email", "Points"], tablefmt="simple"))


def export_csv(session, output_dir: str):
    paths = export_csv_service(session, output_dir)
    print(f"  Schedule written to: {paths['schedule']}")
    print(f"  Points leaderboard written to: {paths['points']}")
    print(f"  Per-person schedule written to: {paths['per_person']}")
    print("\nExport complete.")


def build_parser():
    parser = argparse.ArgumentParser(description="Generate and export the task schedule.")
    sub = parser.add_subparsers(dest="command", required=True)

    schedule_parser = sub.add_parser("schedule", help="Run the scheduling algorithm.")
    schedule_parser.add_argument("--keep-existing", action="store_true", dest="keep_existing", help="Preserve existing assignments and fill only missing slots.")
    sub.add_parser("show", help="Display the current schedule.")

    export_parser = sub.add_parser("export", help="Export the schedule to CSV files.")
    export_parser.add_argument("--output", metavar="DIR", default="./exports", help="Directory for CSV output.")

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
    finally:
        session.close()


if __name__ == "__main__":
    main()
