import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-me')
    DATABASE = str(BASE_DIR / 'instance' / 'emp.sqlite3')
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    CACHE_TTL = int(os.getenv('CACHE_TTL', '60'))
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@emp.local')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Admin@123')

