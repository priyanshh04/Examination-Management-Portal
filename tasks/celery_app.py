import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
celery = Celery('emp', broker=REDIS_URL, backend=REDIS_URL)
celery.conf.task_always_eager = os.getenv('CELERY_TASK_ALWAYS_EAGER', '0') == '1'
celery.conf.timezone = os.getenv('CELERY_TIMEZONE', 'Asia/Kolkata')
celery.conf.enable_utc = True
celery.conf.task_track_started = True
celery.conf.result_expires = 86400
celery.conf.beat_schedule = {
    'daily-examination-reminders': {'task': 'emp.daily_reminders', 'schedule': crontab(hour=int(os.getenv('DAILY_REMINDER_HOUR','9')), minute=int(os.getenv('DAILY_REMINDER_MINUTE','0')))},
    'monthly-examination-report': {'task': 'emp.monthly_report', 'schedule': crontab(day_of_month='1', hour=0, minute=15)},
}

def make_celery(app):
    c = Celery(app.import_name, broker=app.config['REDIS_URL'], backend=app.config['REDIS_URL'])
    c.conf.update(task_always_eager=os.getenv('CELERY_TASK_ALWAYS_EAGER', '0') == '1')
    return c

