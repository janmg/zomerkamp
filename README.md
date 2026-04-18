# Zomerkamp Task Roster

A four-application Python system for fairly scheduling volunteers across a 4-day event. Data is stored in MariaDB via SQLAlchemy.

## Project Structure

```text
zomerkamp/
|- config.py               # Database credentials and event constants
|- models.py               # SQLAlchemy ORM models and DB helpers
|- requirements.txt
|
|- app1_import.py          # CLI: import tasks and participants from CSV
|- app2_schedule.py        # CLI: generate fair schedule, export CSV
|- app3_admin.py           # CLI: admin and override management
|
|- app4_web/
|  |- app.py               # Flask web application
|  |- templates/
|     |- base.html
|     |- leaderboard.html
|     |- schedule.html
|     |- master.html
|
|- sample_tasks.csv        # Example tasks CSV
|- sample_participants.csv # Example participants CSV
```

## Quick Start

### 1. Database Setup (MariaDB)

```sql
CREATE DATABASE zomerkamp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'zomerkamp_user'@'localhost' IDENTIFIED BY 'change_me';
GRANT ALL PRIVILEGES ON zomerkamp.* TO 'zomerkamp_user'@'localhost';
FLUSH PRIVILEGES;
```

Edit `config.py` to match your credentials.

### 2. Python Environment

```bash
pip install -r requirements.txt
```

### 3. Initialize Tables

```bash
python app1_import.py --init-db
```

## App 1: CSV Import (`app1_import.py`)

Reads two CSV files and upserts their data into the database. Re-running is safe: existing rows are updated, not duplicated.

```bash
python app1_import.py --tasks sample_tasks.csv --participants sample_participants.csv
```

### `tasks.csv` Format

| Column | Description |
|---|---|
| `task_name` | Name of the task |
| `day` | Day number (1-4) |
| `begin_time` | Start time (`HH:MM`) |
| `end_time` | End time (`HH:MM`) |
| `points` | Points earned for doing this task |
| `people_required` | Number of volunteers needed |

The time block (`morning`, `afternoon`, `evening`) is derived automatically from the midpoint of begin/end time.

### `participants.csv` Format

| Column | Description |
|---|---|
| `name` | Full name |
| `email` | Email address (unique key) |
| `phone` | Phone number (optional) |
| `day1_morning` ... `day4_evening` | `TRUE` / `FALSE` availability per block |
| `preference` | One of: `serving snacks`, `serving food`, `cleaning after food`, `cleaning toilets`, `organize afternoon games`, `do not care` |

## App 2: Scheduler (`app2_schedule.py`)

### Subcommands

| Command | Description |
|---|---|
| `schedule` | Clear assignments and run the fair-scheduling algorithm |
| `schedule --keep-existing` | Schedule only unassigned tasks |
| `show` | Print current schedule to the terminal |
| `export --output DIR` | Write three CSV files to `DIR` |
| `backup` | Refresh the backup person for every task |

```bash
python app2_schedule.py schedule
python app2_schedule.py show
python app2_schedule.py export --output ./exports
python app2_schedule.py backup
```

### Scheduling Algorithm

1. Tasks are processed in day/time order.
2. For each task, eligible candidates are people who:
   - are available in that day + time block
   - have no `Unavailability` record blocking them
3. Candidates are ranked by lowest projected total points after assignment, with preference match used as a tie-breaker.
4. The first candidate becomes the lead (earns points); the rest are helpers (earn points).
5. One additional eligible person is assigned as backup (earns no points).

### Export CSVs

Three files are written with a timestamp in the filename:

- `schedule_<ts>.csv`: one row per assignment (all tasks x all people)
- `points_<ts>.csv`: leaderboard sorted by points
- `per_person_<ts>.csv`: alphabetical list of people with their tasks

## App 3: Admin (`app3_admin.py`)

### Subcommands

```bash
# List all participants with accumulated points
python app3_admin.py list-people

# List all tasks (optionally filter by day)
python app3_admin.py list-tasks
python app3_admin.py list-tasks --day 2

# Show unavailability records with IDs
python app3_admin.py list-unavailable

# Mark unavailable for a specific task
python app3_admin.py set-unavailable --person "Alice" --task 7

# Mark unavailable for an entire day
python app3_admin.py set-unavailable --person "Bob" --day 3

# Mark unavailable for all days
python app3_admin.py set-unavailable --person "Charlie" --all-days

# Remove an unavailability record (use list-unavailable to find the UID)
python app3_admin.py remove-unavailable --id 4

# Promote backup to helper (awards points) and select a new backup
python app3_admin.py confirm-backup --task 7

# Manually set the lead for a task
python app3_admin.py set-lead --task 7 --person "Grace"

# Remove a person from a task; auto-promotes lead and refreshes backup
python app3_admin.py remove-assignment --task 7 --person "Bob"
```

When a person is set unavailable, their assignments in the affected scope are removed and backups are refreshed automatically.

## App 4: Web (`app4_web/app.py`)

```bash
cd app4_web
python app.py
# http://localhost:5000
```

### Routes

| URL | Description |
|---|---|
| `/` | Redirects to `/leaderboard` |
| `/leaderboard` | Participants ranked by points earned |
| `/schedule` | All participants (A-Z) with their task assignments and points |
| `/master` | Master sheet: all activities by day/time with lead, helpers, backup, and contact details |

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
