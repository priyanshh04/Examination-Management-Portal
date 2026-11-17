import csv, io, os, sqlite3, smtplib, json
from urllib.request import Request, urlopen
from email.message import EmailMessage
from datetime import date, timedelta
from .celery_app import celery, make_celery

def _db():
    path=os.getenv('EMP_DATABASE') or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'emp.sqlite3')
    db=sqlite3.connect(path); db.row_factory=sqlite3.Row; return db

def _mail(subject, body, recipient):
    webhook=os.getenv('NOTIFICATION_WEBHOOK_URL')
    if webhook:
        payload=json.dumps({'text':f'{subject}\n{body}'}).encode('utf8')
        req=Request(webhook,data=payload,headers={'Content-Type':'application/json'},method='POST')
        with urlopen(req,timeout=15): pass
        return True
    host=os.getenv('MAIL_SERVER')
    if not host:return False
    msg=EmailMessage(); msg['Subject']=subject; msg['From']=os.getenv('MAIL_USERNAME','emp@localhost'); msg['To']=recipient; msg.set_content(body)
    with smtplib.SMTP(host, int(os.getenv('MAIL_PORT','587')), timeout=15) as smtp:
        if os.getenv('MAIL_USERNAME'): smtp.starttls(); smtp.login(os.getenv('MAIL_USERNAME'), os.getenv('MAIL_PASSWORD',''))
        smtp.send_message(msg)
    return True

@celery.task(name='emp.daily_reminders')
def daily_reminders():
    db=_db(); rows=db.execute('SELECT b.student_id,u.email,x.name,s.date,s.start_time,s.end_time,ex.name examiner,x.instructions FROM bookings b JOIN users u ON u.id=b.student_id JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN users ex ON ex.id=s.examiner_id WHERE b.status="Booked" AND s.date BETWEEN date("now") AND date("now","+1 day")').fetchall(); sent=0
    for r in rows:
        body=f"{r['name']}\nDate: {r['date']} {r['start_time']} - {r['end_time']}\nExaminer: {r['examiner']}\nInstructions: {r['instructions'] or 'Please arrive on time.'}"
        try:
            if _mail('Examination reminder',body,r['email']):sent+=1
        except Exception: pass
    db.close(); return {'found':len(rows),'sent':sent}

@celery.task(name='emp.monthly_report')
def monthly_report():
    db=_db(); stats=db.execute('SELECT COUNT(DISTINCT x.id) exams,COUNT(DISTINCT ev.student_id) students,COUNT(DISTINCT CASE WHEN b.status="Completed" THEN b.id END) completed,COUNT(DISTINCT CASE WHEN b.status="Booked" AND ev.id IS NULL THEN b.id END) pending FROM examinations x LEFT JOIN slots s ON s.examination_id=x.id LEFT JOIN bookings b ON b.slot_id=s.id LEFT JOIN evaluations ev ON ev.booking_id=b.id WHERE strftime("%Y-%m",s.date)=strftime("%Y-%m",date("now","-1 month"))').fetchone(); top=db.execute('SELECT u.name,COUNT(b.id) total FROM users u LEFT JOIN slots s ON s.examiner_id=u.id LEFT JOIN bookings b ON b.slot_id=s.id WHERE u.role="examiner" GROUP BY u.id ORDER BY total DESC LIMIT 5').fetchall(); html=f"<html><body><h1>Monthly Examination Report</h1><p>Examinations: {stats['exams']} | Students evaluated: {stats['students']} | Completed bookings: {stats['completed']} | Pending evaluations: {stats['pending']}</p><h2>Most active examiners</h2><ul>"+''.join(f"<li>{r['name']}: {r['total']} bookings</li>" for r in top)+"</ul></body></html>"; path=os.path.join(os.path.dirname(os.path.dirname(__file__)),'instance','monthly_report.html'); open(path,'w',encoding='utf8').write(html)
    try:_mail('Monthly examination report',html,os.getenv('ADMIN_REPORT_EMAIL',os.getenv('ADMIN_EMAIL','admin@emp.local')))
    except Exception:pass
    db.close(); return {'file':path}

@celery.task(name='emp.student_history_export')
def student_history_export(user_id, job_id):
    db=_db(); rows=db.execute('SELECT x.name examination,c.name course,s.date,ex.name examiner,COALESCE(ev.total_marks,"") marks,b.status FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=s.examiner_id LEFT JOIN evaluations ev ON ev.booking_id=b.id WHERE b.student_id=?',(user_id,)).fetchall(); path=os.path.join(os.path.dirname(os.path.dirname(__file__)),'instance',f'export_{job_id}.csv'); os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',newline='',encoding='utf8') as f:
        w=csv.writer(f); w.writerow(['Student ID','Examination Name','Course','Examination Date','Examiner','Marks Obtained','Booking Status']); w.writerows([[user_id,r['examination'],r['course'],r['date'],r['examiner'],r['marks'],r['status']] for r in rows])
    db.execute('UPDATE jobs SET status="Completed",filename=? WHERE id=?',(path,job_id)); db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(user_id,'Export ready','Your examination history CSV is ready to download.')); db.commit(); db.close(); return path

def register_tasks(app): return make_celery(app)

