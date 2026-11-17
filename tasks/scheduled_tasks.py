import csv, io, os, sqlite3, smtplib, json, html
from urllib.request import Request, urlopen
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from email.message import EmailMessage
from datetime import date, timedelta
from .celery_app import celery, make_celery

def _db():
    path=os.getenv('EMP_DATABASE') or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'emp.sqlite3')
    db=sqlite3.connect(path); db.row_factory=sqlite3.Row; return db

def _mail(subject, body, recipient, allow_webhook=True):
    webhook=os.getenv('NOTIFICATION_WEBHOOK_URL')
    if allow_webhook and webhook:
        payload=json.dumps({'text':f'{subject}\n{body}'}).encode('utf8')
        req=Request(webhook,data=payload,headers={'Content-Type':'application/json'},method='POST')
        with urlopen(req,timeout=15): pass
        return True
    host=os.getenv('MAIL_SERVER')
    if not host:return False
    msg=EmailMessage(); msg['Subject']=subject; msg['From']=os.getenv('MAIL_USERNAME','emp@localhost'); msg['To']=recipient
    if body.lstrip().lower().startswith('<html'):
        msg.set_content('This message contains an HTML examination report.')
        msg.add_alternative(body, subtype='html')
    else:
        msg.set_content(body)
    with smtplib.SMTP(host, int(os.getenv('MAIL_PORT','587')), timeout=15) as smtp:
        if os.getenv('MAIL_USERNAME'): smtp.starttls(); smtp.login(os.getenv('MAIL_USERNAME'), os.getenv('MAIL_PASSWORD',''))
        smtp.send_message(msg)
    return True

@celery.task(name='emp.daily_reminders')
def daily_reminders():
    db=_db(); rows=db.execute('SELECT b.student_id,u.email,x.name,s.date,s.start_time,s.end_time,ex.name examiner,x.instructions FROM bookings b JOIN users u ON u.id=b.student_id JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN users ex ON ex.id=s.examiner_id WHERE b.status="Booked" AND s.date=date("now","+1 day")').fetchall(); sent=0
    for r in rows:
        body=f"{r['name']}\nDate: {r['date']} {r['start_time']} - {r['end_time']}\nExaminer: {r['examiner']}\nInstructions: {r['instructions'] or 'Please arrive on time.'}"
        try:
            if _mail('Examination reminder',body,r['email']):sent+=1
        except Exception: pass
    db.close(); return {'found':len(rows),'sent':sent}

@celery.task(name='emp.monthly_report')
def monthly_report():
    db=_db()
    period=db.execute("SELECT date('now','start of month','-1 month') start_date,date('now','start of month','-1 day') end_date").fetchone()
    start_date,end_date=period['start_date'],period['end_date']
    stats=db.execute("""
        SELECT COUNT(DISTINCT x.id) exams,
               COUNT(DISTINCT ev.student_id) students_evaluated,
               COUNT(DISTINCT CASE WHEN b.status='Completed' THEN b.id END) completed,
               COUNT(DISTINCT CASE WHEN b.status='Booked' AND ev.id IS NULL THEN b.id END) pending
        FROM examinations x
        LEFT JOIN slots s ON s.examination_id=x.id
        LEFT JOIN bookings b ON b.slot_id=s.id
        LEFT JOIN evaluations ev ON ev.booking_id=b.id
        WHERE s.date BETWEEN ? AND ? AND x.status='Completed'
    """,(start_date,end_date)).fetchone()
    top=db.execute("""
        SELECT u.name,COUNT(DISTINCT ev.id) evaluations,COUNT(DISTINCT b.id) bookings
        FROM users u
        LEFT JOIN slots s ON s.examiner_id=u.id AND s.date BETWEEN ? AND ?
        LEFT JOIN bookings b ON b.slot_id=s.id
        LEFT JOIN evaluations ev ON ev.booking_id=b.id
        WHERE u.role='examiner'
        GROUP BY u.id ORDER BY evaluations DESC,bookings DESC LIMIT 5
    """,(start_date,end_date)).fetchall()
    examiner_rows=''.join(f"<tr><td>{html.escape(r['name'])}</td><td>{r['evaluations']}</td><td>{r['bookings']}</td></tr>" for r in top)
    report=f"""<!doctype html><html><head><meta charset="utf-8"><title>Monthly Examination Report</title></head>
    <body><h1>Monthly Examination Report</h1><p>Period: {start_date} to {end_date}</p>
    <ul><li>Examinations conducted: {stats['exams']}</li><li>Students evaluated: {stats['students_evaluated']}</li>
    <li>Completed bookings: {stats['completed']}</li><li>Pending evaluations: {stats['pending']}</li></ul>
    <h2>Most active examiners</h2><table border="1" cellpadding="6"><tr><th>Examiner</th><th>Evaluations</th><th>Bookings</th></tr>{examiner_rows}</table></body></html>"""
    path=os.path.join(os.path.dirname(os.path.dirname(__file__)),'instance','monthly_report.html')
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',encoding='utf8') as report_file: report_file.write(report)
    db.close()
    recipient=os.getenv('ADMIN_REPORT_EMAIL',os.getenv('ADMIN_EMAIL','admin@emp.local'))
    try:
        sent=_mail('Monthly examination report',report,recipient,allow_webhook=False)
    except Exception:
        sent=False
    return {'file':path,'email_sent':sent,'period_start':start_date,'period_end':end_date}

@celery.task(name='emp.student_history_export')
def student_history_export(user_id, job_id):
    db=_db()
    path=os.path.join(os.path.dirname(os.path.dirname(__file__)),'instance',f'export_{job_id}.csv')
    try:
        records=db.execute('SELECT x.name examination,c.name course,s.date,ex.name examiner,COALESCE(ev.total_marks,"") marks,b.status FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=s.examiner_id LEFT JOIN evaluations ev ON ev.booking_id=b.id WHERE b.student_id=?',(user_id,)).fetchall()
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,'w',newline='',encoding='utf8') as output:
            writer=csv.writer(output)
            writer.writerow(['Student ID','Examination Name','Course','Examination Date','Examiner','Marks Obtained','Booking Status'])
            writer.writerows([[user_id,r['examination'],r['course'],r['date'],r['examiner'],r['marks'],r['status']] for r in records])
        db.execute('UPDATE jobs SET status="Completed",filename=? WHERE id=?',(path,job_id))
        db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(user_id,'Export ready','Your examination history CSV is ready to download.'))
        db.commit()
        return path
    except Exception:
        db.execute('UPDATE jobs SET status="Failed" WHERE id=?',(job_id,))
        db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(user_id,'Export failed','Your examination history export could not be generated. Please try again.'))
        db.commit()
        raise
    finally:
        db.close()

def register_tasks(app): return make_celery(app)

