import os, csv, io, json, sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from database.db import get_db, close_db, init_db

def create_app():
    app=Flask(__name__, template_folder='frontend', static_folder='frontend', static_url_path='/static'); app.config.from_object(Config)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db(); db=get_db(); row=db.execute("SELECT id FROM users WHERE role='admin'").fetchone()
        if not row: db.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',('Administrator',app.config['ADMIN_EMAIL'],generate_password_hash(app.config['ADMIN_PASSWORD']),'admin')); db.commit()
    def ok(data=None,status=200): return jsonify({'ok':True,'data':data}),status
    def fail(msg,status=400): return jsonify({'ok':False,'error':msg}),status
    def user(): return get_db().execute('SELECT * FROM users WHERE id=?',(session.get('uid'),)).fetchone() if session.get('uid') else None
    def auth(roles=None):
        u=user()
        if not u: return None,fail('Authentication required',401)
        if roles and u['role'] not in roles: return None,fail('Forbidden',403)
        return u,None
    def rows(sql,args=()): return [dict(x) for x in get_db().execute(sql,args).fetchall()]
    @app.route('/')
    def index(): return send_file(os.path.join(app.root_path, 'frontend', 'index.html'), mimetype='text/html')
    @app.post('/api/auth/register')
    def register():
        d=request.json or {}; required=['name','email','password']
        if any(not d.get(x) for x in required) or len(d['password'])<6: return fail('Name, email and password (6+ characters) are required')
        try:
            db=get_db(); db.execute('INSERT INTO users(name,email,password_hash,role,contact) VALUES(?,?,?,?,?)',(d['name'],d['email'].lower(),generate_password_hash(d['password']),'student',d.get('contact'))); db.commit(); return ok({'message':'Registration successful'},201)
        except sqlite3.IntegrityError: return fail('Email already registered',409)
    @app.post('/api/auth/login')
    def login():
        d=request.json or {}; u=get_db().execute('SELECT * FROM users WHERE email=?',(d.get('email','').lower(),)).fetchone()
        if not u or not check_password_hash(u['password_hash'],d.get('password','')) or u['status']!='Active': return fail('Invalid credentials',401)
        session.clear(); session['uid']=u['id']; return ok({'user':{k:u[k] for k in ('id','name','email','role','department')}})
    @app.post('/api/auth/logout')
    def logout(): session.clear(); return ok({'message':'Logged out'})
    @app.get('/api/auth/me')
    def me():
        u,err=auth()
        return err or ok({k:u[k] for k in ('id','name','email','role','contact','department')})
    @app.get('/api/dashboard')
    def dashboard():
        u,err=auth()
        if err:return err
        db=get_db(); r={}
        if u['role']=='admin':
            for key,table in [('courses','courses'),('examinations','examinations'),('students','users WHERE role="student"'),('examiners','users WHERE role="examiner"'),('slots','slots'),('bookings','bookings')]: r[key]=db.execute('SELECT COUNT(*) n FROM '+table).fetchone()['n']
            r['pending_evaluations']=db.execute("SELECT COUNT(*) n FROM bookings b LEFT JOIN evaluations e ON e.booking_id=b.id WHERE b.status='Booked' AND e.id IS NULL").fetchone()['n']; r['completed_examinations']=db.execute("SELECT COUNT(*) n FROM examinations WHERE status='Completed'").fetchone()['n']
        elif u['role']=='examiner':
            r['assigned_examinations']=db.execute('SELECT COUNT(DISTINCT examination_id) n FROM slots WHERE examiner_id=?',(u['id'],)).fetchone()['n']; r['created_slots']=db.execute('SELECT COUNT(*) n FROM slots WHERE examiner_id=?',(u['id'],)).fetchone()['n']; r['booked_students']=db.execute('SELECT COUNT(*) n FROM bookings b JOIN slots s ON s.id=b.slot_id WHERE s.examiner_id=? AND b.status="Booked"',(u['id'],)).fetchone()['n']; r['pending_evaluations']=db.execute('SELECT COUNT(*) n FROM bookings b JOIN slots s ON s.id=b.slot_id LEFT JOIN evaluations e ON e.booking_id=b.id WHERE s.examiner_id=? AND e.id IS NULL',(u['id'],)).fetchone()['n']
        else:
            r['available_examinations']=db.execute("SELECT COUNT(*) n FROM examinations WHERE status IN ('Booking Open','Slot Creation')").fetchone()['n']; r['bookings']=db.execute('SELECT COUNT(*) n FROM bookings WHERE student_id=?',(u['id'],)).fetchone()['n']; r['results']=db.execute('SELECT COUNT(*) n FROM evaluations e JOIN bookings b ON b.id=e.booking_id JOIN examinations x ON x.id=(SELECT examination_id FROM slots WHERE id=b.slot_id) WHERE b.student_id=? AND x.published=1',(u['id'],)).fetchone()['n']
        return ok(r)
    @app.route('/api/courses',methods=['GET','POST'])
    def courses():
        if request.method=='GET': return ok(rows('SELECT * FROM courses ORDER BY id DESC'))
        u,e=auth(['admin']);
        if e:return e
        d=request.json or {}; 
        if not d.get('code') or not d.get('name'): return fail('Code and name are required')
        try: db=get_db(); db.execute('INSERT INTO courses(code,name,description) VALUES(?,?,?)',(d['code'],d['name'],d.get('description',''))); db.commit(); return ok({'message':'Course created'},201)
        except sqlite3.IntegrityError:return fail('Course code already exists',409)
    @app.route('/api/examinations',methods=['GET','POST'])
    def examinations():
        if request.method=='GET': return ok(rows('SELECT x.*,c.code course_code,c.name course_name FROM examinations x JOIN courses c ON c.id=x.course_id ORDER BY x.id DESC'))
        u,e=auth(['admin']);
        if e:return e
        d=request.json or {}; fields=['course_id','name','type','duration','max_marks']
        if any(d.get(x) in (None,'') for x in fields): return fail('Course, name, type, duration and maximum marks are required')
        db=get_db(); db.execute('INSERT INTO examinations(course_id,name,type,duration,max_marks,slot_start,slot_end,booking_start,booking_end,status,instructions) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(d['course_id'],d['name'],d['type'],d['duration'],d['max_marks'],d.get('slot_start'),d.get('slot_end'),d.get('booking_start'),d.get('booking_end'),d.get('status','Booking Open'),d.get('instructions',''))); db.commit(); return ok({'message':'Examination created'},201)
    @app.get('/api/examinations/<int:eid>')
    def exam_detail(eid):
        u,e=auth();
        if e:return e
        x=get_db().execute('SELECT x.*,c.name course_name,c.code course_code FROM examinations x JOIN courses c ON c.id=x.course_id WHERE x.id=?',(eid,)).fetchone()
        if not x:return fail('Examination not found',404)
        return ok({**dict(x),'rubrics':rows('SELECT * FROM rubrics WHERE examination_id=?',(eid,)),'slots':rows('SELECT s.*,u.name examiner FROM slots s JOIN users u ON u.id=s.examiner_id WHERE s.examination_id=?',(eid,))})
    @app.post('/api/rubrics')
    def rubric():
        u,e=auth(['admin']);
        if e:return e
        d=request.json or {}; db=get_db(); db.execute('INSERT INTO rubrics(examination_id,criterion,max_marks,weightage,description) VALUES(?,?,?,?,?)',(d.get('examination_id'),d.get('criterion'),d.get('max_marks'),d.get('weightage',100),d.get('description',''))); db.commit(); return ok({'message':'Rubric added'},201)
    @app.get('/api/users')
    def users():
        u,e=auth(['admin']);
        return e or ok(rows("SELECT id,name,email,role,department,status FROM users WHERE role!='admin' ORDER BY name"))
    @app.post('/api/examiners')
    def examiner():
        u,e=auth(['admin']);
        if e:return e
        d=request.json or {}
        try: db=get_db(); db.execute('INSERT INTO users(name,email,password_hash,role,department,contact) VALUES(?,?,?,?,?,?)',(d['name'],d['email'],generate_password_hash(d.get('password','Examiner@123')),'examiner',d.get('department'),d.get('contact'))); db.commit(); return ok({'message':'Examiner created'},201)
        except (KeyError,sqlite3.IntegrityError):return fail('Valid unique name and email required',409)
    @app.route('/api/slots',methods=['GET','POST'])
    def slots():
        u,e=auth();
        if e:return e
        db=get_db()
        if request.method=='GET': return ok(rows('SELECT s.*,x.name examination,u.name examiner FROM slots s JOIN examinations x ON x.id=s.examination_id JOIN users u ON u.id=s.examiner_id ORDER BY s.date,s.start_time'))
        if u['role'] not in ('admin','examiner'):return fail('Only examiners or admin can create slots',403)
        d=request.json or {}; eid=d.get('examination_id'); ex=db.execute('SELECT * FROM examinations WHERE id=?',(eid,)).fetchone()
        if not ex:return fail('Examination not found',404)
        examiner_id=u['id'] if u['role']=='examiner' else d.get('examiner_id')
        overlap=db.execute('SELECT id FROM slots WHERE examiner_id=? AND date=? AND start_time<? AND end_time>?',(examiner_id,d.get('date'),d.get('end_time'),d.get('start_time'))).fetchone()
        if overlap:return fail('Overlapping slot for examiner')
        cap=int(d.get('capacity',1)); db.execute('INSERT INTO slots(examination_id,examiner_id,date,start_time,end_time,capacity,available,meeting_link) VALUES(?,?,?,?,?,?,?,?)',(eid,examiner_id,d.get('date'),d.get('start_time'),d.get('end_time'),cap,cap,d.get('meeting_link'))); db.commit(); return ok({'message':'Slot created'},201)
    @app.post('/api/bookings')
    def book():
        u,e=auth(['student']);
        if e:return e
        d=request.json or {}; db=get_db()
        try:
            db.execute('BEGIN IMMEDIATE'); s=db.execute('SELECT s.*,x.name FROM slots s JOIN examinations x ON x.id=s.examination_id WHERE s.id=?',(d.get('slot_id'),)).fetchone()
            if not s or s['available']<=0 or s['status']!='OPEN': raise ValueError('Slot is full or unavailable')
            if db.execute('SELECT b.id FROM bookings b JOIN slots z ON z.id=b.slot_id WHERE b.student_id=? AND z.examination_id=? AND b.status="Booked"',(u['id'],s['examination_id'])).fetchone(): raise ValueError('You already have a booking for this examination')
            db.execute('INSERT INTO bookings(student_id,slot_id) VALUES(?,?)',(u['id'],s['id'])); db.execute('UPDATE slots SET available=available-1,status=CASE WHEN available-1=0 THEN "FULL" ELSE status END WHERE id=?',(s['id'],)); db.commit(); return ok({'message':'Booking confirmed'},201)
        except ValueError as ex: db.rollback(); return fail(str(ex))
        except sqlite3.IntegrityError: db.rollback(); return fail('Duplicate booking',409)
    @app.get('/api/bookings')
    def bookings():
        u,e=auth();
        if e:return e
        q='SELECT b.*,x.name examination,x.max_marks,s.date,s.start_time,s.end_time,ex.name examiner,c.name course FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN users ex ON ex.id=s.examiner_id JOIN courses c ON c.id=x.course_id WHERE b.student_id=?' if u['role']=='student' else 'SELECT b.*,x.name examination,s.date,s.start_time,st.name student,ex.name examiner FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN users st ON st.id=b.student_id JOIN users ex ON ex.id=s.examiner_id WHERE '+('s.examiner_id=?' if u['role']=='examiner' else '1=1')
        return ok(rows(q,(u['id'],) if u['role']!='admin' else ()))
    @app.post('/api/evaluations')
    def evaluate():
        u,e=auth(['examiner']);
        if e:return e
        d=request.json or {}; db=get_db(); b=db.execute('SELECT b.*,s.examiner_id,s.examination_id FROM bookings b JOIN slots s ON s.id=b.slot_id WHERE b.id=?',(d.get('booking_id'),)).fetchone()
        if not b or b['examiner_id']!=u['id']:return fail('Booking is not assigned to you',403)
        if db.execute('SELECT id FROM evaluations WHERE booking_id=?',(b['id'],)).fetchone():return fail('Evaluation already submitted',409)
        rub=rows('SELECT * FROM rubrics WHERE examination_id=?',(b['examination_id'],)); total=sum(float(i.get('marks',0)) for i in d.get('details',[])); maxm=float(db.execute('SELECT max_marks FROM examinations WHERE id=?',(b['examination_id'],)).fetchone()['max_marks'])
        if total>maxm:return fail('Marks exceed examination maximum')
        db.execute('INSERT INTO evaluations(booking_id,student_id,examiner_id,total_marks,remarks) VALUES(?,?,?,?,?)',(b['id'],b['student_id'],u['id'],total,d.get('remarks',''))); eid=db.execute('SELECT last_insert_rowid()').fetchone()[0]
        for x in d.get('details',[]): db.execute('INSERT INTO evaluation_details(evaluation_id,rubric_id,marks,comments) VALUES(?,?,?,?)',(eid,x['rubric_id'],x['marks'],x.get('comments','')))
        db.execute('UPDATE bookings SET status="Completed" WHERE id=?',(b['id'],)); db.commit(); return ok({'message':'Evaluation submitted'})
    @app.get('/api/results')
    def results():
        u,e=auth();
        if e:return e
        q='SELECT ev.*,x.name examination,c.name course,ex.name examiner FROM evaluations ev JOIN bookings b ON b.id=ev.booking_id JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=ev.examiner_id WHERE x.published=1 AND b.student_id=?' if u['role']=='student' else 'SELECT ev.*,x.name examination,c.name course,st.name student FROM evaluations ev JOIN bookings b ON b.id=ev.booking_id JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users st ON st.id=ev.student_id'
        return ok(rows(q,(u['id'],) if u['role']=='student' else ()))
    @app.post('/api/examinations/<int:eid>/publish')
    def publish(eid):
        u,e=auth(['admin']);
        if e:return e
        db=get_db(); db.execute('UPDATE examinations SET published=1,status="Completed" WHERE id=?',(eid,)); db.commit(); return ok({'message':'Results published'})
    @app.get('/api/export.csv')
    def export_csv():
        u,e=auth(['student']);
        if e:return e
        data=rows('SELECT x.name examination,c.name course,s.date,ex.name examiner,COALESCE(ev.total_marks,"") marks,b.status FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=s.examiner_id LEFT JOIN evaluations ev ON ev.booking_id=b.id WHERE b.student_id=?',(u['id'],)); out=io.StringIO(); w=csv.DictWriter(out,fieldnames=['examination','course','date','examiner','marks','status']); w.writeheader(); w.writerows(data); return send_file(io.BytesIO(out.getvalue().encode()),as_attachment=True,download_name='examination-history.csv',mimetype='text/csv')
    return app
