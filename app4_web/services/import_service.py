"""CSV import helpers shared by CLI and web flows."""

from __future__ import annotations

import csv
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import TextIO

from sqlalchemy.exc import IntegrityError

from config import AFTERNOON_END_HOUR, EVENT_DAYS, MORNING_END_HOUR, PREFERENCES, TIME_BLOCKS
from models import Participant, Task


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


def _build_task_reader(handle: TextIO) -> csv.DictReader:
    return csv.DictReader(handle)


def _build_participant_reader(handle: TextIO) -> csv.DictReader:
    return csv.DictReader(handle)


def import_tasks_from_handle(handle: TextIO, session) -> dict:
    imported = 0
    skipped = 0
    updated = 0
    added = 0
    warnings: list[str] = []

    reader = _build_task_reader(handle)
    for row_number, row in enumerate(reader, start=2):
        try:
            task_name = row["task_name"].strip()
            day = int(row["day"].strip())
            begin_time = parse_time(row["begin_time"])
            end_time = parse_time(row["end_time"])
            points = int(float(row["points"].strip()))
            people_required = int(row["people_required"].strip())
        except (KeyError, ValueError) as exc:
            warnings.append(f"tasks row {row_number} skipped - {exc}")
            skipped += 1
            continue

        time_block = infer_time_block(begin_time, end_time)
        existing = session.query(Task).filter_by(name=task_name, day=day, begin_time=begin_time).first()
        if existing:
            existing.end_time = end_time
            existing.points = points
            existing.people_required = people_required
            existing.time_block = time_block
            updated += 1
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
            added += 1
        imported += 1

    session.commit()
    return {
        "imported": imported,
        "skipped": skipped,
        "added": added,
        "updated": updated,
        "warnings": warnings,
    }


def import_participants_from_handle(handle: TextIO, session) -> dict:
    availability_fields = [f"day{day}_{block}" for day in range(1, EVENT_DAYS + 1) for block in TIME_BLOCKS]
    imported = 0
    skipped = 0
    updated = 0
    added = 0
    warnings: list[str] = []

    reader = _build_participant_reader(handle)
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
            warnings.append(f"participants row {row_number} skipped - {exc}")
            skipped += 1
            continue

        participant = session.query(Participant).filter_by(email=email).first()
        if participant is None:
            participant = Participant(name=name, email=email)
            session.add(participant)
            session.flush()
            added += 1
        else:
            updated += 1

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
        raise ValueError(f"Database integrity error: {exc.orig}") from exc

    return {
        "imported": imported,
        "skipped": skipped,
        "added": added,
        "updated": updated,
        "warnings": warnings,
    }


def import_tasks_from_csv_path(csv_path: str, session) -> dict:
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        return import_tasks_from_handle(handle, session)


def import_participants_from_csv_path(csv_path: str, session) -> dict:
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        return import_participants_from_handle(handle, session)
