# Installation Guide

## 1. Configure MariaDB

```sql
CREATE DATABASE zomerkamp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'zomerkamp_user'@'10.0.0.%' IDENTIFIED BY 'change_me';
GRANT ALL PRIVILEGES ON zomerkamp.* TO 'zomerkamp_user'@'localhost';
FLUSH PRIVILEGES;
```

If you are running everything locally, you can also create the user on `localhost` instead of `10.0.0.%`.

## 2. Create environment settings

Create a `.env` file in this folder:

```env
DB_USER=zomerkamp_user
DB_PASSWORD=change_me
DB_HOST=localhost
DB_PORT=3306
DB_NAME=zomerkamp
```

## 3. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Initialize the database

```bash
python app1_import.py --init-db
```

You can also initialize the tables from the web interface on the Import page.

## 5. Load data

You now have two supported options.

### Option A: Web upload flow

Start the web server:

```bash
python app4_web/app.py
```

Then open `http://localhost:5000/import` and:

1. Initialize the database tables if needed.
2. Upload `tasks.csv` and/or `participants.csv`.
3. Continue to `/operations` to run scheduling or export CSV files.

### Option B: CLI flow

```bash
python app1_import.py --tasks sample_tasks.csv --participants sample_participants.csv
```

## 6. Run the scheduler

You can also do this from the web interface at `http://localhost:5000/operations`.

```bash
python app2_schedule.py schedule
```

To preserve existing assignments and only fill gaps:

```bash
python app2_schedule.py schedule --keep-existing
```

## 7. Useful commands

```bash
python app2_schedule.py show
python app2_schedule.py export --output ./exports
python app2_schedule.py backup
python app3_admin.py list-people
python app3_admin.py list-tasks --day 2
python app3_admin.py set-unavailable --person "Alice" --day 2 --reason "Unavailable"
python app3_admin.py confirm-backup --task 5
python app3_admin.py set-lead --task 5 --person "Grace"
python app3_admin.py remove-assignment --task 5 --person "Bob"
python app4_web/app.py
```

## 8. Web interface

Start the Flask application:

```bash
python app4_web/app.py
```

Available pages:

- `/`: dashboard and links to all app areas
- `/import`: upload tasks and participants CSV files
- `/operations`: run scheduler, refresh backups, export CSV files
- `/admin`: manage unavailability, leads, backups, and assignments
- `/leaderboard`: participant ranking by points
- `/schedule`: per-participant schedule view
- `/master`: full task overview by day

## 9. Code layout

The application is now split into reusable layers:

- `app1_import.py`, `app2_schedule.py`, `app3_admin.py`: CLI entry points
- `app4_web/app.py`: Flask entry point
- `app4_web/routes/`: web routes grouped by feature
- `app4_web/services/`: shared business logic used by both web and CLI flows
- `models.py`, `roster_logic.py`: database models and scheduling helpers