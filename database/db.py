import sqlite3, os
from flask import current_app, g
def get_db():
    if 'db' not in g:
        g.db=sqlite3.connect(current_app.config['DATABASE'], timeout=20)
        g.db.row_factory=sqlite3.Row; g.db.execute('PRAGMA foreign_keys=ON')
    return g.db
def close_db(e=None):
    db=g.pop('db',None)
    if db: db.close()
def init_db():
    os.makedirs(os.path.dirname(current_app.config['DATABASE']), exist_ok=True)
    db=get_db()
    with open(os.path.join(os.path.dirname(__file__),'schema.sql'),encoding='utf8') as schema_file:
        db.executescript(schema_file.read())
    # Migrate the original broad uniqueness rule so cancelled bookings remain history.
    db.execute('DROP INDEX IF EXISTS one_active_booking')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking ON bookings(student_id,slot_id) WHERE status='Booked'")
    db.commit()
