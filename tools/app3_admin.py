#!/usr/bin/env python3
"""Administrative management for the merged Zomerkamp roster."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tabulate import tabulate

from web.services import admin_service
from models import get_session


def cmd_list_people(session, _args):
    participants = admin_service.list_people(session)
    rows = []
    for participant in participants:
        rows.append([
            participant["id"],
            participant["name"],
            participant["email"],
            participant["phone"],
            participant["preference"],
            participant["points"],
            participant["remarks"],
            "YES" if participant["excluded"] else "no",
        ])
    print(tabulate(rows, headers=["ID", "Name", "Email", "Phone", "Preference", "Points", "Remarks", "Excluded"], tablefmt="rounded_outline"))


def cmd_list_tasks(session, args):
    tasks = admin_service.list_tasks(session, day=args.day)
    rows = []
    for task in tasks:
        rows.append([
            task["id"],
            task["day"],
            task["time"],
            task["name"],
            task["block"],
            task["points"],
            task["required"],
            task["lead"],
            task["helpers"],
        ])
    print(tabulate(rows, headers=["TID", "Day", "Time", "Task", "Block", "Pts", "Req", "Lead", "Helpers"], tablefmt="rounded_outline"))


def cmd_list_unavailable(session, _args):
    rows = []
    for record in admin_service.list_unavailable(session):
        rows.append([record["id"], record["participant"], record["scope"], record["task"], record["reason"]])
    if not rows:
        print("No unavailability records.")
        return
    print(tabulate(rows, headers=["UID", "Participant", "Scope", "Task", "Reason"], tablefmt="rounded_outline"))


def cmd_set_unavailable(session, args):
    mode = "all-days" if args.all_days else ("day" if args.day else "task")
    value = args.day if args.day else args.task
    try:
        message = admin_service.set_unavailable(session, args.person, args.reason, mode=mode, value=value)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    print(f"[OK] {message}")


def cmd_remove_unavailable(session, args):
    try:
        message = admin_service.remove_unavailable(session, args.id)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    print(f"[OK] {message}")


def cmd_set_lead(session, args):
    try:
        message = admin_service.set_lead(session, args.task, args.person)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    print(f"[OK] {message}")


def cmd_remove_assignment(session, args):
    try:
        message = admin_service.remove_assignment(session, args.task, args.person)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
    print(f"[OK] {message}")


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

    set_lead_parser = sub.add_parser("set-lead", help="Set the lead for a task.")
    set_lead_parser.add_argument("--task", type=int, required=True, metavar="TASK_ID")
    set_lead_parser.add_argument("--person", required=True, help="Participant name, partial match allowed.")

    remove_assignment_parser = sub.add_parser("remove-assignment", help="Remove a person from a task.")
    remove_assignment_parser.add_argument("--task", type=int, required=True, metavar="TASK_ID")
    remove_assignment_parser.add_argument("--person", required=True, help="Participant name, partial match allowed.")

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
        elif args.command == "set-lead":
            cmd_set_lead(session, args)
        elif args.command == "remove-assignment":
            cmd_remove_assignment(session, args)
    finally:
        session.close()


if __name__ == "__main__":
    main()
