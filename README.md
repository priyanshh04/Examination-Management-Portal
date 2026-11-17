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

Open http://127.0.0.1:5000. The default Admin credentials are `admin@emp.local` / `Admin@123` unless changed in `.env`. Database tables and the Admin are created automatically. Redis is required for Celery; install Redis for Windows via Docker (`docker run --name emp-redis -p 6379:6379 -d redis`) or Memurai.

Run background services in separate PowerShell windows:

```powershell
.\.venv\Scripts\Activate.ps1
celery -A tasks.scheduled_tasks worker --loglevel=INFO --pool=solo
celery -A tasks.scheduled_tasks beat --loglevel=INFO
```

The daily reminder, monthly HTML report, and student CSV export tasks are implemented in `tasks/scheduled_tasks.py`. Configure SMTP through `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, and `ADMIN_REPORT_EMAIL`.

## Demo flow

Log in as Admin, create a course, create an examination using the course ID, create an examiner account, then use the examiner account/API to create a slot. Register a student, book the slot, evaluate through `/api/evaluations`, publish as Admin, and inspect Results/CSV as the student.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Or run the complete Windows verification script:

```powershell
.\verify.ps1
```

Start the application with:

```powershell
.\run.ps1
```

