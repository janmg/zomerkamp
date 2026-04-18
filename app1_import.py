#!/usr/bin/env python3
"""Import tasks and participants from CSV files into the database."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, time as dt_time

from sqlalchemy.exc import IntegrityError

from config import AFTERNOON_END_HOUR, MORNING_END_HOUR, PREFERENCES, TIME_BLOCKS
from models import Participant, Task, get_session, init_db


def parse_bool(value: str) -> bool:
    return value.strip().upper() in {"TRUE", "1", "YES", "Y"}


def parse_time(value: str) -> dt_time:
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value.strip(), fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse time: {value!r}")


def infer_time_block(begin_time: dt_time, end_time: dt_time) -> str:
    midpoint_hour = ((begin_time.hour * 60 + begin_time.minute) + (end_time.hour * 60 + end_time.minute)) / 120
    if midpoint_hour < MORNING_END_HOUR:
        return "morning"
    if midpoint_hour < AFTERNOON_END_HOUR:
        return "afternoon"
    return "evening"


def import_tasks(csv_path: str, session) -> int:
    imported = 0
    skipped = 0
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            try:
                task_name = row["task_name"].strip()
                day = int(row["day"].strip())
                begin_time = parse_time(row["begin_time"])
                end_time = parse_time(row["end_time"])
                points = int(float(row["points"].strip()))
                people_required = int(row["people_required"].strip())
            except (KeyError, ValueError) as exc:
                print(f"  [WARN] tasks row {row_number} skipped - {exc}")
                skipped += 1
                continue

            time_block = infer_time_block(begin_time, end_time)
            existing = session.query(Task).filter_by(name=task_name, day=day, begin_time=begin_time).first()
            if existing:
                existing.end_time = end_time
                existing.points = points
                existing.people_required = people_required
                existing.time_block = time_block
                print(f"  [UPDATE] Task '{task_name}' day {day} updated.")
            else:
                session.add(
                    Task(
                        name=task_name,
                        day=day,
                        begin_time=begin_time,
                        end_time=end_time,
                        points=points,
                        people_required=people_required,
                        time_block=time_block,
                    )
                )
                print(f"  [ADD]    Task '{task_name}' day {day} ({time_block}) added.")
            imported += 1
    session.commit()
    print(f"\nTasks: {imported} processed, {skipped} skipped.\n")
    return imported


def import_participants(csv_path: str, session) -> int:
    availability_fields = [f"day{day}_{block}" for day in range(1, 5) for block in TIME_BLOCKS]
    imported = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            try:
                name = row["name"].strip()
                email = row["email"].strip().lower()
                phone = row.get("phone", "").strip() or None
                remarks = row.get("remarks", "").strip() or None
                preference = row.get("preference", "do not care").strip().lower()
                if preference not in PREFERENCES:
                    preference = "do not care"
                availability_map = {field: parse_bool(row.get(field, "FALSE")) for field in availability_fields}
            except (KeyError, ValueError) as exc:
                print(f"  [WARN] participants row {row_number} skipped - {exc}")
                skipped += 1
                continue

            participant = session.query(Participant).filter_by(email=email).first()
            if participant is None:
                participant = Participant(name=name, email=email)
                session.add(participant)
                session.flush()
                print(f"  [ADD]    Participant '{name}' ({email}) added.")
            else:
                print(f"  [UPDATE] Participant '{name}' ({email}) updated.")

            participant.name = name
            participant.phone = phone
            participant.preference = preference
            participant.remarks = remarks
            for field, available in availability_map.items():
                day_str, block = field.split("_")
                participant.set_block_availability(int(day_str.replace("day", "")), block, available)

            imported += 1

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        print(f"[ERROR] Database integrity error: {exc.orig}")
        return 0

    print(f"\nParticipants: {imported} processed, {skipped} skipped.\n")
    return imported


def build_parser():
    parser = argparse.ArgumentParser(description="Import tasks and participants from CSV files.")
    parser.add_argument("--tasks", metavar="CSV", help="Path to tasks CSV file.")
    parser.add_argument("--participants", metavar="CSV", help="Path to participants CSV file.")
    parser.add_argument("--init-db", action="store_true", dest="init_db", help="Create database tables and exit.")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not (args.init_db or args.tasks or args.participants):
        parser.print_help()
        sys.exit(1)

    print("Initialising database...")
    init_db()
    if args.init_db and not args.tasks and not args.participants:
        print("Done.")
        return

    session = get_session()
    try:
        if args.tasks:
            print(f"\n=== Importing tasks from: {args.tasks} ===")
            import_tasks(args.tasks, session)
        if args.participants:
            print(f"\n=== Importing participants from: {args.participants} ===")
            import_participants(args.participants, session)
    except FileNotFoundError as exc:
        print(f"[ERROR] File not found: {exc}")
        sys.exit(1)
    finally:
        session.close()

    print("Import complete.")


if __name__ == "__main__":
    main()