# Zomerkamp Task Roster

Zomerkamp is a volunteer scheduling system for a 4-day event. It stores participants, tasks, assignments, and exceptions in MariaDB via SQLAlchemy, and exposes the workflow both through CLI entry points and a modular Flask web app.

The main flows from the old app1-app3 scripts now also exist inside the web server:

- app1: CSV import through `/import`
- app2: scheduling and export operations through `/operations`
- app3: admin overrides and assignment management through `/admin`

## Project Structure

```text
zomerkamp/
|- config.py                    # Database credentials and event constants
|- models.py                    # SQLAlchemy ORM models and DB helpers
|- roster_logic.py              # Candidate ranking and scheduling helpers
|- requirements.txt
|
|- app1_import.py               # CLI entry point: CSV import
|- app2_schedule.py             # CLI entry point: scheduler and export
|- app3_admin.py                # CLI entry point: admin operations
|
|- app4_web/
|  |- __init__.py               # Flask app factory
|  |- app.py                    # Flask startup entry point
|  |- routes/
|  |  |- dashboard.py           # Read-only dashboard pages
|  |  |- imports.py             # Upload/import web flow
|  |  |- operations.py          # Scheduling/export web flow
|  |  |- admin.py               # Admin management web flow
|  |
|  |- services/
|  |  |- import_service.py      # Shared import logic
|  |  |- schedule_service.py    # Shared scheduling/export logic
|  |  |- admin_service.py       # Shared admin logic
|  |
|  |- templates/                # Flask HTML templates
|  |- static/                   # Static assets
|
|- sample_tasks.csv             # Example tasks CSV
|- sample_participants.csv      # Example participants CSV
|- INSTALLATION.md              # Setup and run instructions
```

## Quick Start

### 1. Install and configure

Follow [INSTALLATION.md](INSTALLATION.md) for the full MariaDB and environment setup.

### 2. Create tables

```bash
python app1_import.py --init-db
```

### 3. Start the web app

```bash
python app4_web/app.py
```

Open `http://localhost:5000`.

### 4. Load sample data

You can either:

- go to `/import` and upload `sample_tasks.csv` and `sample_participants.csv`
- or use the CLI:

```bash
python app1_import.py --tasks sample_tasks.csv --participants sample_participants.csv
```

### 5. Generate a schedule

Either use `/operations` in the browser or run:

```bash
python app2_schedule.py schedule
```

## Web Interface

The web app is now the main operational surface.

| URL | Description |
|---|---|
| `/` | Dashboard with navigation and summary metrics |
| `/import` | Initialize DB tables and upload tasks/participants CSV files |
| `/operations` | Run the scheduler, refresh backups, export CSV files |
| `/admin` | Manage unavailability, backups, leads, and assignments |
| `/leaderboard` | Participants ranked by points earned |
| `/schedule` | Per-participant schedule view |
| `/master` | Master sheet across all days and tasks |

## CLI Entry Points

The CLI tools still work, but now call the same shared service layer used by the web app.

### `app1_import.py`

Imports task and participant CSV data.

```bash
python app1_import.py --init-db
python app1_import.py --tasks sample_tasks.csv --participants sample_participants.csv
```

### `app2_schedule.py`

Scheduler and export commands.

```bash
python app2_schedule.py schedule
python app2_schedule.py schedule --keep-existing
python app2_schedule.py show
python app2_schedule.py export --output ./exports
python app2_schedule.py backup
```

### `app3_admin.py`

Admin and override commands.

```bash
python app3_admin.py list-people
python app3_admin.py list-tasks --day 2
python app3_admin.py list-unavailable
python app3_admin.py set-unavailable --person "Alice" --day 2 --reason "Unavailable"
python app3_admin.py confirm-backup --task 5
python app3_admin.py set-lead --task 5 --person "Grace"
python app3_admin.py remove-assignment --task 5 --person "Bob"
```

## CSV Formats

### `tasks.csv`

| Column | Description |
|---|---|
| `task_name` | Name of the task |
| `day` | Day number (1-4) |
| `begin_time` | Start time (`HH:MM` or `HH:MM:SS`) |
| `end_time` | End time (`HH:MM` or `HH:MM:SS`) |
| `points` | Points earned for doing this task |
| `people_required` | Number of volunteers needed |

The system derives the time block (`morning`, `afternoon`, `evening`) automatically from the task midpoint.

### `participants.csv`

| Column | Description |
|---|---|
| `name` | Full name |
| `email` | Email address (unique key) |
| `phone` | Phone number (optional) |
| `remarks` | Free text notes (optional) |
| `day1_morning` ... `day4_evening` | `TRUE` / `FALSE` availability per block |
| `preference` | One of: `serving snacks`, `serving food`, `cleaning after food`, `cleaning toilets`, `organize afternoon games`, `do not care` |

## Scheduling Rules

1. Tasks are processed in day/time order.
2. Eligible candidates must be available for the task's day and time block.
3. Unavailability rules are respected for all-days, per-day, and per-task exclusions.
4. Candidates are ranked by fairness first: lowest projected total points wins.
5. Preference matching is used as a tie-breaker.
6. The first active assignee becomes `lead`; remaining required people become `helper`.
7. One additional eligible participant is selected as `backup` when possible.

## Export Output

The export flow writes three timestamped CSV files:

- `schedule_<ts>.csv`: one row per assignment
- `points_<ts>.csv`: leaderboard by total points
- `per_person_<ts>.csv`: assignments grouped by participant

## Data Model Overview

### Participant

- `id`, `name`, `email`, `phone`
- `day1_morning` ... `day4_evening`
- `preference`
- `excluded_all_days`

### Assignment

- `id`
- `task_id`
- `participant_id`
- `role`
- `points_awarded`

### Task

- `id`, `name`, `day`
- `begin_time`, `end_time`
- `points`, `people_required`
- `time_block`

### Unavailability

- `participant_id`
- `task_id` (nullable, specific task)
- `day` (nullable, whole day)
- `all_days` (boolean)

## Roles

- `lead`: first person assigned, earns points
- `helper`: additional required people, earn points
- `backup`: standby person, earns no points until confirmed via `confirm-backup`

## Architecture Notes

- `app4_web/services/` contains the shared business logic used by both web routes and CLI scripts.
- `app4_web/routes/` keeps Flask routes grouped by feature instead of putting all views in one file.
- The CLI remains useful for scripting, while the browser now supports the same operational workflows.
