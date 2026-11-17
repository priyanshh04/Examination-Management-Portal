import json
import redis

def client(url):
    try:
        c=redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2)
        c.ping(); return c
    except Exception:
        return None

def get_json(url, key):
    c=client(url)
    if not c:return None
    try:
        value=c.get(key); return json.loads(value) if value else None
    except Exception:return None

def set_json(url, key, value, ttl):
    c=client(url)
    if not c:return False
    try:c.setex(key, ttl, json.dumps(value)); return True
    except Exception:return False

def invalidate(url, *keys):
    c=client(url)
    if not c:return False
    try:c.delete(*keys); return True
    except Exception:return False
