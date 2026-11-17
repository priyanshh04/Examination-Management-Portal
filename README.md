# Examination Management Portal

Local Flask + Vue + Bootstrap examination management system using SQLite, direct `sqlite3`, Redis-compatible Celery configuration, sessions, role authorization, bookings, evaluations, publication and CSV history export.

## Windows PowerShell

```powershell
cd Examination-Management-Portal
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

The daily reminder, monthly HTML report, and student CSV export tasks are implemented in `tasks/scheduled_tasks.py`. Configure SMTP through `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, and `ADMIN_REPORT_EMAIL`. Daily reminders can alternatively use `NOTIFICATION_WEBHOOK_URL`. Set `CELERY_TIMEZONE` if your deployment is not in Asia/Kolkata. Monthly report delivery requires working SMTP credentials; the report is also saved as HTML under `instance/monthly_report.html`.

## Demo flow

Log in as Admin, create a course and an examination in **Slot Creation** status, create an examiner account, and assign that examiner to the examination from the examination list. Sign in as the examiner and create one or more slots. Return as Admin and change the examination to **Booking Open**. Register a student, book a slot, evaluate the booking in the Evaluation workspace, publish the result as Admin, and inspect the scorecard/history as the student. The examiner can only create slots for examinations assigned by Admin.

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

