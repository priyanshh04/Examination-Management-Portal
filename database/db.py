import sqlite3, os
from flask import current_app, g


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'], timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
        g.db.execute('PRAGMA busy_timeout=30000')
    return g.db


def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Create missing schema objects and apply safe additive migrations.

    Existing database files and rows are intentionally retained. CREATE IF NOT
    EXISTS plus guarded ALTER TABLE statements make initialization repeatable.
    """
    database_path = current_app.config['DATABASE']
    os.makedirs(os.path.dirname(database_path), exist_ok=True)
    db = get_db()
    db.execute('PRAGMA journal_mode=WAL')
    with open(os.path.join(os.path.dirname(__file__), 'schema.sql'), encoding='utf8') as schema_file:
        db.executescript(schema_file.read())

    # Additive migrations for databases created by earlier EMP V2 iterations.
    migrations = {
        'users': {
            'contact': 'TEXT',
            'department': 'TEXT',
            'status': "TEXT NOT NULL DEFAULT 'Active'",
        },
        'examinations': {
            'slot_start': 'TEXT',
            'slot_end': 'TEXT',
            'booking_start': 'TEXT',
            'booking_end': 'TEXT',
            'instructions': 'TEXT',
            'published': 'INTEGER NOT NULL DEFAULT 0',
        },
        'slots': {
            'available': 'INTEGER NOT NULL DEFAULT 0',
            'status': "TEXT NOT NULL DEFAULT 'OPEN'",
            'meeting_link': 'TEXT',
        },
        'bookings': {
            'booking_date': 'TEXT',
            'status': "TEXT NOT NULL DEFAULT 'Booked'",
        },
    }
    for table, columns in migrations.items():
        existing = {row['name'] for row in db.execute(f'PRAGMA table_info({table})').fetchall()}
        for column, declaration in columns.items():
            if column not in existing:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}')

    # Rebuild only the active-booking index; cancelled rows remain as history.
    db.execute('DROP INDEX IF EXISTS one_active_booking')
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking ON bookings(student_id,slot_id) WHERE status='Booked'")
    db.execute('CREATE INDEX IF NOT EXISTS idx_slots_exam_date ON slots(examination_id,date,start_time)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_slots_examiner_date ON slots(examiner_id,date,start_time)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_bookings_slot_status ON bookings(slot_id,status)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_bookings_student_status ON bookings(student_id,status)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_evaluations_student ON evaluations(student_id)')
    db.commit()
