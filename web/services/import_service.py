"""CSV import helpers shared by CLI and web flows."""

from __future__ import annotations

import csv
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import TextIO

from sqlalchemy.exc import IntegrityError

from config import AFTERNOON_END_HOUR, EVENT_DAYS, MORNING_END_HOUR, PREFERENCES, TIME_BLOCKS
from models import Participant, Task

DUTCH_DAY_TO_INDEX = {
    "woensdag": 1,
    "donderdag": 2,
    "vrijdag": 3,
    "zaterdag": 4,
}

SURVEY_SLOT_TO_BLOCK = {
    "Mijn beschikbaarheid als hulpouder is: [07:00 - 07:30]": "morning",
    "Mijn beschikbaarheid als hulpouder is: [07:30 - 09:00]": "morning",
    "Mijn beschikbaarheid als hulpouder is: [09:00 - 13:00]": "morning",
    "Mijn beschikbaarheid als hulpouder is: [13:00 - 15:30]": "afternoon",
    "Mijn beschikbaarheid als hulpouder is: [15:30 - 18:00]": "afternoon",
    "Mijn beschikbaarheid als hulpouder is: [18:00 - 21:00]": "evening",
}


def parse_bool(value: str) -> bool:
    return value.strip().upper() in {"TRUE", "1", "YES", "Y", "JA", "J"}


def parse_days(value: str) -> set[int]:
    days: set[int] = set()
    for token in value.split(","):
        token_clean = token.strip().lower()
        if not token_clean:
            continue
        for dutch_name, day_index in DUTCH_DAY_TO_INDEX.items():
            if dutch_name in token_clean:
                days.add(day_index)
                break
    return days


def parse_group(value: str) -> str | None:
    group_value = value.strip().lower()
    if not group_value:
        return None
    group_value = group_value.replace("groep", "").strip()
    if group_value in {"1", "2", "3a", "3b", "4", "5", "6+7", "8"}:
        return group_value
    return None


def parse_messaging(value: str) -> str:
    raw = value.strip().lower()
    if "signal" in raw:
        return "signal"
    if "telegram" in raw:
        return "telegram"
    if "sms" in raw:
        return "sms"
    if "whatsapp" in raw or "what'sapp" in raw or "whats app" in raw:
        return "whatsapp"
    return "whatsapp"


def build_survey_availability(row: dict[str, str]) -> dict[str, bool]:
    availability_fields = [f"day{day}_{block}" for day in range(1, EVENT_DAYS + 1) for block in TIME_BLOCKS]
    availability_map = {field: False for field in availability_fields}

    for slot_column, block in SURVEY_SLOT_TO_BLOCK.items():
        for day in parse_days(row.get(slot_column, "")):
            availability_map[f"day{day}_{block}"] = True

    return availability_map


def is_survey_row(row: dict[str, str]) -> bool:
    return "Naam Ouder" in row and "E-mail Ouder" in row and "Voornaam Kind" in row


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
            if is_survey_row(row):
                name = row["Naam Ouder"].strip()
                email = row["E-mail Ouder"].strip().lower()
                phone = row.get("Telefoonnummer Ouder", "").strip() or None
                preference = "do not care"
                availability_map = build_survey_availability(row)
                child_notes = row.get("Opmerkingen:", "").strip() or None
                avail_notes = row.get("Opmerkingen beschikbaarheid:", "").strip() or None
                remarks_parts = [part for part in [child_notes, avail_notes] if part]
                remarks = " | ".join(remarks_parts) if remarks_parts else None
            else:
                name = row["name"].strip()
                email = row["email"].strip().lower()
                phone = row.get("phone", "").strip() or None
                remarks = row.get("remarks", "").strip() or None
                preference = row.get("preference", "do not care").strip().lower()
                if preference not in PREFERENCES:
                    preference = "do not care"
                availability_map = {field: parse_bool(row.get(field, "FALSE")) for field in availability_fields}

            if not name:
                raise ValueError("missing name")
            if not email:
                raise ValueError("missing email")
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

        if is_survey_row(row):
            participant.submitted_at = row.get("Tijdstempel", "").strip() or None
            participant.child_first = row.get("Voornaam Kind", "").strip() or None
            participant.child_last = row.get("Achternaam Kind", "").strip() or None
            participant.group = parse_group(row.get("Groep", ""))
            participant.child_att_d1 = row.get("Aanwezigheid van het kind [Woensdag]", "").strip() or None
            participant.child_att_d2 = row.get("Aanwezigheid van het kind [Donderdag]", "").strip() or None
            participant.child_att_d3 = row.get("Aanwezigheid van het kind [Vrijdag]", "").strip() or None
            participant.child_att_d4 = row.get("Aanwezigheid van het kind [Zaterdag]", "").strip() or None
            participant.child_diet = row.get(
                "Geef hier eventuele allergieën of dieetwensen (bijv. vegetarisch, veganistisch) van uw kind aan:",
                "",
            ).strip() or None
            participant.child_notes = row.get("Opmerkingen:", "").strip() or None
            participant.first_ntc = parse_bool(row.get("Dit is mijn eerste NTC zomerkamp", ""))
            participant.sleep_pref = row.get("Ik blijf slapen op het kamp:", "").strip() or None
            participant.sleep_notes = row.get("Opmerkingen overnachten:", "").strip() or None
            participant.avail_notes = row.get("Opmerkingen beschikbaarheid:", "").strip() or None
            participant.has_car = parse_bool(
                row.get("Heeft u een auto beschikbaar (om bijvoorbeeld leerkrachten van het station op te halen)", "")
            )
            participant.parent_diet = row.get("Eventuele voedselallergieën Ouder:", "").strip() or None
            participant.survey_chat = row.get("Chat apps", "").strip() or None
            participant.messaging = parse_messaging(row.get("Chat apps", ""))

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
