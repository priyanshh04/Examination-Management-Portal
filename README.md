# Examination Management Portal

Local Flask + Vue + Bootstrap examination management system using SQLite, direct `sqlite3`, Redis-compatible Celery configuration, sessions, role authorization, bookings, evaluations, publication and CSV history export.

## Windows PowerShell

```powershell
cd EMP
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open http://127.0.0.1:5000. The default Admin credentials are `admin@emp.local` / `Admin@123` unless changed in `.env`. Database tables and the Admin are created automatically. Redis is optional for the core HTTP workflows; install Redis for Windows via Docker (`docker run -p 6379:6379 redis`) or Memurai. Start a worker with `celery -A tasks.scheduled_tasks worker --loglevel=INFO`. Celery task stubs for daily reminders and monthly reports are registered in `tasks/scheduled_tasks.py`; SMTP/webhook credentials are intentionally environment-based.

## Demo flow

Log in as Admin, create a course, create an examination using the course ID, create an examiner account, then use the examiner account/API to create a slot. Register a student, book the slot, evaluate through `/api/evaluations`, publish as Admin, and inspect Results/CSV as the student.

## Tests

```powershell
python -m unittest discover -s tests -v
```

