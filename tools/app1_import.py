#!/usr/bin/env python3
"""Import tasks and participants from CSV files into the database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from web.services.import_service import import_participants_from_csv_path, import_tasks_from_csv_path
from models import get_session, init_db


def import_tasks(csv_path: str, session) -> int:
    summary = import_tasks_from_csv_path(csv_path, session)
    print(
        f"\nTasks: {summary['imported']} processed, {summary['skipped']} skipped "
        f"({summary['added']} added, {summary['updated']} updated).\n"
    )
    for warning in summary["warnings"]:
        print(f"  [WARN] {warning}")
    return summary["imported"]


def import_participants(csv_path: str, session) -> int:
    summary = import_participants_from_csv_path(csv_path, session)
    print(
        f"\nParticipants: {summary['imported']} processed, {summary['skipped']} skipped "
        f"({summary['added']} added, {summary['updated']} updated).\n"
    )
    for warning in summary["warnings"]:
        print(f"  [WARN] {warning}")
    return summary["imported"]


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
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    finally:
        session.close()

    print("Import complete.")


if __name__ == "__main__":
    main()
