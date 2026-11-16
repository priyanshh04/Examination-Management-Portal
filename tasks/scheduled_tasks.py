from .celery_app import celery, make_celery
@celery.task(name='emp.daily_reminders')
def daily_reminders(): return 'Reminder scan completed'
@celery.task(name='emp.monthly_report')
def monthly_report(): return 'Monthly report generation completed'
def register_tasks(app): return make_celery(app)

