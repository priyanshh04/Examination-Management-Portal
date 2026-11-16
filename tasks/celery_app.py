import os
from celery import Celery
celery = Celery('emp', broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'), backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0')) def make_celery(app):
def make_celery(app):
    c=Celery(app.import_name, broker=app.config['REDIS_URL'], backend=app.config['REDIS_URL']); c.conf.update(task_always_eager=os.getenv('CELERY_TASK_ALWAYS_EAGER','0')=='1'); return c

