#!/usr/bin/env python3
"""Flask web front-end for the merged Zomerkamp roster."""

from __future__ import annotations

import os
import sys
from collections import defaultdict

from flask import Flask, render_template

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Participant, Task, get_session
from roster_logic import compute_total_points

app = Flask(__name__, template_folder="templates")


@app.route("/")
def index():
    session = get_session()
    try:
        participant_count = session.query(Participant).count()
        task_count = session.query(Task).count()
        assigned_count = sum(1 for participant in session.query(Participant).all() for _ in participant.assignments)
        top_volunteer = None
        totals = compute_total_points(session)
        if totals:
            winner = max(session.query(Participant).all(), key=lambda participant: totals.get(participant.id, 0), default=None)
            if winner is not None:
                top_volunteer = {"name": winner.name, "points": totals.get(winner.id, 0)}
    finally:
        session.close()
    return render_template(
        "index.html",
        participant_count=participant_count,
        task_count=task_count,
        assigned_count=assigned_count,
        top_volunteer=top_volunteer,
    )


@app.route("/leaderboard")
def leaderboard():
    session = get_session()
    try:
        totals = compute_total_points(session)
        participants = sorted(session.query(Participant).all(), key=lambda participant: (totals.get(participant.id, 0), participant.name.lower()), reverse=True)
        rows = []
        for rank, participant in enumerate(participants, start=1):
            active_tasks = sum(1 for assignment in participant.assignments if assignment.role in {"lead", "helper"})
            rows.append(
                {
                    "rank": rank,
                    "name": participant.name,
                    "email": participant.email,
                    "phone": participant.phone or "-",
                    "preference": participant.preference,
                    "remarks": participant.remarks or "-",
                    "points": totals.get(participant.id, 0),
                    "task_count": active_tasks,
                }
            )
    finally:
        session.close()
    return render_template("leaderboard.html", rows=rows)


@app.route("/schedule")
def schedule():
    session = get_session()
    try:
        totals = compute_total_points(session)
        people = []
        for participant in sorted(session.query(Participant).all(), key=lambda person: person.name.lower()):
            tasks = []
            for assignment in sorted(participant.assignments, key=lambda item: (item.task.day, item.task.begin_time, item.task.name)):
                tasks.append(
                    {
                        "day": assignment.task.day,
                        "begin": assignment.task.begin_time.strftime("%H:%M"),
                        "end": assignment.task.end_time.strftime("%H:%M"),
                        "name": assignment.task.name,
                        "block": assignment.task.time_block,
                        "role": assignment.role,
                        "points": assignment.points_awarded,
                    }
                )
            people.append(
                {
                    "name": participant.name,
                    "email": participant.email,
                    "phone": participant.phone or "-",
                    "preference": participant.preference,
                    "remarks": participant.remarks or "-",
                    "total_points": totals.get(participant.id, 0),
                    "tasks": tasks,
                }
            )
    finally:
        session.close()
    return render_template("schedule.html", people=people)


@app.route("/master")
def master():
    session = get_session()
    try:
        by_day: dict[int, list] = defaultdict(list)
        for task in session.query(Task).order_by(Task.day, Task.begin_time, Task.name).all():
            assignments = sorted(task.assignments, key=lambda item: (["lead", "helper", "backup"].index(item.role), item.participant.name.lower()))
            by_day[task.day].append(
                {
                    "id": task.id,
                    "name": task.name,
                    "begin": task.begin_time.strftime("%H:%M"),
                    "end": task.end_time.strftime("%H:%M"),
                    "points": task.points,
                    "people_required": task.people_required,
                    "time_block": task.time_block,
                    "assignment_count": len(assignments),
                    "lead": next((assignment for assignment in assignments if assignment.role == "lead"), None),
                    "helpers": [assignment for assignment in assignments if assignment.role == "helper"],
                    "backup": next((assignment for assignment in assignments if assignment.role == "backup"), None),
                    "all_assigned": assignments,
                }
            )
    finally:
        session.close()
    return render_template("master.html", by_day=dict(sorted(by_day.items())))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)