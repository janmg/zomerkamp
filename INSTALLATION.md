# Installation Guide

## 1. Configure MariaDB

```sql
CREATE DATABASE zomerkamp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'zomerkamp_user'@'localhost' IDENTIFIED BY 'change_me';
GRANT ALL PRIVILEGES ON zomerkamp.* TO 'zomerkamp_user'@'localhost';
FLUSH PRIVILEGES;
```

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

## 4. Initialize and load sample data

```bash
python app1_import.py --init-db
python app1_import.py --tasks sample_tasks.csv --participants sample_participants.csv
python app2_schedule.py schedule
```

## 5. Useful commands

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