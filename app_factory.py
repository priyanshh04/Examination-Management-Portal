import os, csv, io, json, sqlite3, secrets
from datetime import datetime
from flask import Flask, request, jsonify, session, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from database.db import get_db, close_db, init_db
from backend.cache import get_json, set_json, invalidate

def create_app():
    app=Flask(__name__, template_folder='frontend', static_folder='frontend', static_url_path='/static'); app.config.from_object(Config)
    app.teardown_appcontext(close_db)
    @app.before_request
    def enforce_csrf():
        if request.path.startswith('/api/') and request.method in ('POST','PUT','PATCH','DELETE') and request.path not in ('/api/auth/login','/api/auth/register'):
            expected=session.get('_csrf')
            provided=request.headers.get('X-CSRF-Token') or request.cookies.get('emp_csrf')
            if not expected or provided != expected:return fail('CSRF token missing or invalid',403)
    @app.after_request
    def expose_csrf(response):
        if '_csrf' not in session:session['_csrf']=secrets.token_urlsafe(24)
        response.set_cookie('emp_csrf',session['_csrf'],httponly=False,samesite='Lax')
        return response
    @app.errorhandler(Exception)
    def handle_unexpected(error):
        app.logger.exception('Unhandled request error')
        return jsonify({'ok':False,'error':'The server could not complete this request. Check the application log.'}),500
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
    def paging():
        try: page=max(1,int(request.args.get('page','1'))); size=min(100,max(1,int(request.args.get('per_page','50'))))
        except ValueError: page,size=1,50
        return page,size,(page-1)*size
    @app.route('/')
    def index():
        path=os.path.join(app.root_path,'frontend','portal.html')
        with open(path,encoding='utf8') as page_file: html=page_file.read()
        # Keep credentials out of the rendered page; configure the seeded Admin in .env.
        html=html.replace('<main class="flex-grow-1 p-4">','<main class="flex-grow-1 p-4"><div v-if="me && me.role===\'admin\'" class="text-end mb-2"><a class="btn btn-sm btn-outline-primary" href="/admin/students">Manage students</a></div>')
        html=html.replace('{{x.status}}</td></tr>','{{x.status}}</td><td><button class="btn btn-sm btn-outline-danger" @click="toggleExaminer(x)">{{x.status===\'Active\'?\'Deactivate\':\'Activate\'}}</button><button class="btn btn-sm btn-outline-secondary ms-1" @click="editExaminer(x)">Edit</button></td></tr>')
        html=html.replace('<button class="btn btn-sm btn-outline-danger" @click="deactivateCourse(x.id)">Deactivate</button>','<button class="btn btn-sm btn-outline-danger" @click="deactivateCourse(x.id)">Deactivate</button><button class="btn btn-sm btn-outline-secondary ms-1" @click="editCourse(x)">Edit</button>')
        html=html.replace('<td>{{x.available}} / {{x.capacity}}</td><td><button v-if="me.role===\'student\'"','<td>{{x.available}} / {{x.capacity}}</td><td><button v-if="me.role===\'admin\'||me.role===\'examiner\'" class="btn btn-sm btn-outline-secondary me-1" @click="editSlot(x)">Edit</button><button v-if="me.role===\'admin\'||me.role===\'examiner\'" class="btn btn-sm btn-outline-danger me-1" @click="deleteSlot(x.id)">Delete</button><button v-if="me.role===\'student\'"')
        html=html.replace('<button v-if="me.role===\'student\'&&x.status===\'Booked\'" class="btn btn-sm btn-outline-danger" @click="cancel(x.id)">Cancel</button>','<button v-if="(me.role===\'student\'||me.role===\'admin\')&&x.status===\'Booked\'" class="btn btn-sm btn-outline-danger me-1" @click="cancel(x.id)">Cancel</button><button v-if="me.role===\'admin\'&&x.status===\'Booked\'" class="btn btn-sm btn-outline-secondary" @click="rescheduleBooking(x)">Reschedule</button>')
        html=html.replace('async createExaminer(){','async editCourse(x){let name=prompt(\'Course name\',x.name);if(name)try{await this.api(\'/courses/\'+x.id,{method:\'PUT\',body:JSON.stringify({name})});await this.load()}catch(e){this.error=e.message}},async editExaminer(x){let name=prompt(\'Examiner name\',x.name);if(name)try{await this.api(\'/users/\'+x.id,{method:\'PUT\',body:JSON.stringify({name})});await this.load()}catch(e){this.error=e.message}},async toggleExaminer(x){try{await this.api(\'/users/\'+x.id,{method:\'PUT\',body:JSON.stringify({status:x.status===\'Active\'?\'Inactive\':\'Active\'})});await this.load()}catch(e){this.error=e.message}},async editSlot(x){let d=prompt(\'Date YYYY-MM-DD\',x.date);if(d)try{await this.api(\'/slots/\'+x.id,{method:\'PUT\',body:JSON.stringify({date:d})});await this.load()}catch(e){this.error=e.message}},async deleteSlot(id){if(confirm(\'Delete this slot?\'))try{await this.api(\'/slots/\'+id,{method:\'DELETE\'});await this.load()}catch(e){this.error=e.message}},async rescheduleBooking(x){let slot_id=prompt(\'New slot ID\');if(slot_id)try{await this.api(\'/bookings/\'+x.id+\'/reschedule\',{method:\'PUT\',body:JSON.stringify({slot_id:Number(slot_id)})});await this.load()}catch(e){this.error=e.message}},async createExaminer(){')
        html=html.replace('duration:60','duration:Number(prompt(\'Duration in minutes\',\'60\'))||60')
        return Response(html,mimetype='text/html')
    @app.route('/examiner/evaluations')
    def examiner_evaluations_page(): return send_file(os.path.join(app.root_path, 'frontend', 'evaluator.html'), mimetype='text/html')
    @app.route('/admin/rubrics')
    def admin_rubrics_page(): return send_file(os.path.join(app.root_path, 'frontend', 'rubrics.html'), mimetype='text/html')
    @app.route('/notifications')
    def notifications_page(): return send_file(os.path.join(app.root_path, 'frontend', 'notifications.html'), mimetype='text/html')
    @app.route('/admin/students')
    def admin_students_page(): return send_file(os.path.join(app.root_path, 'frontend', 'students.html'), mimetype='text/html')
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
    @app.get('/api/auth/csrf')
    def csrf_token(): return ok({'token':session.setdefault('_csrf',secrets.token_urlsafe(24))})
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
            r['available_examinations']=db.execute("SELECT COUNT(*) n FROM examinations WHERE status='Booking Open'").fetchone()['n']; r['bookings']=db.execute('SELECT COUNT(*) n FROM bookings WHERE student_id=?',(u['id'],)).fetchone()['n']; r['results']=db.execute('SELECT COUNT(*) n FROM evaluations e JOIN bookings b ON b.id=e.booking_id JOIN examinations x ON x.id=(SELECT examination_id FROM slots WHERE id=b.slot_id) WHERE b.student_id=? AND x.published=1',(u['id'],)).fetchone()['n']
        return ok(r)
    @app.route('/api/courses',methods=['GET','POST'])
    def courses():
        if request.method=='GET':
            page,size,offset=paging(); q=request.args.get('q','').strip(); params=[]; where=''
            if q: where='WHERE code LIKE ? OR name LIKE ?'; params=[f'%{q}%',f'%{q}%']
            data=rows(f'SELECT * FROM courses {where} ORDER BY id DESC LIMIT ? OFFSET ?',params+[size,offset]); return ok(data)
        u,e=auth(['admin']);
        if e:return e
        d=request.json or {}; 
        if not d.get('code') or not d.get('name'): return fail('Code and name are required')
        try: db=get_db(); db.execute('INSERT INTO courses(code,name,description) VALUES(?,?,?)',(d['code'],d['name'],d.get('description',''))); db.commit(); return ok({'message':'Course created'},201)
        except sqlite3.IntegrityError:return fail('Course code already exists',409)
    @app.route('/api/examinations',methods=['GET','POST'])
    def examinations():
        if request.method=='GET':
            viewer,auth_error=auth()
            if auth_error:return auth_error
            cached=get_json(app.config['REDIS_URL'],'emp:examinations')
            if cached is None:
                cached=rows('SELECT x.*,c.code course_code,c.name course_name FROM examinations x JOIN courses c ON c.id=x.course_id ORDER BY x.id DESC'); set_json(app.config['REDIS_URL'],'emp:examinations',cached,app.config['CACHE_TTL'])
            if viewer['role']=='student':cached=[x for x in cached if x['status']=='Booking Open']
            elif viewer['role']=='examiner':
                assigned={r['examination_id'] for r in rows('SELECT examination_id FROM exam_assignments WHERE examiner_id=? UNION SELECT examination_id FROM slots WHERE examiner_id=?',(viewer['id'],viewer['id']))}
                cached=[x for x in cached if x['id'] in assigned]
            q=request.args.get('q','').lower(); typ=request.args.get('type'); status=request.args.get('status'); filtered=[x for x in cached if (not q or q in x['name'].lower() or q in x['course_name'].lower()) and (not typ or x['type']==typ) and (not status or x['status']==status)]; page,size,offset=paging(); return ok(filtered[offset:offset+size])
        u,e=auth(['admin']);
        if e:return e
        d=request.json or {}; fields=['course_id','name','type','duration','max_marks']
        if any(d.get(x) in (None,'') for x in fields): return fail('Course, name, type, duration and maximum marks are required')
        if d['type'] not in ('Viva','Practical','Project Demo','Assessment'):return fail('Unsupported examination type')
        if d.get('status','Draft') not in ('Draft','Slot Creation','Booking Open','Closed','Completed'):return fail('Invalid examination status')
        try:
            if int(d['duration'])<=0 or float(d['max_marks'])<=0:return fail('Duration and maximum marks must be positive')
        except (TypeError,ValueError):return fail('Duration and maximum marks must be numeric')
        timeline=[d.get(x) for x in ('slot_start','slot_end','booking_start','booking_end') if d.get(x)]
        try:
            parsed=[datetime.fromisoformat(x.replace('Z','+00:00')).replace(tzinfo=None) for x in timeline]
            if len(parsed)==4 and not (parsed[0]<=parsed[1] and parsed[2]<=parsed[3]):return fail('Examination timeline is inconsistent')
        except ValueError:return fail('Examination timeline must use ISO date/time values')
        db=get_db(); course_ref=str(d['course_id']).strip()
        course=db.execute('SELECT id FROM courses WHERE status="Active" AND (CAST(id AS TEXT)=? OR code=?)',(course_ref,course_ref)).fetchone()
        if not course:return fail('Course ID/code does not exist or is inactive. Use a value shown on the Courses page.',400)
        try:
            db.execute('INSERT INTO examinations(course_id,name,type,duration,max_marks,slot_start,slot_end,booking_start,booking_end,status,instructions) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(course['id'],d['name'],d['type'],d['duration'],d['max_marks'],d.get('slot_start'),d.get('slot_end'),d.get('booking_start'),d.get('booking_end'),d.get('status','Booking Open'),d.get('instructions',''))); db.commit()
        except sqlite3.IntegrityError:return fail('Examination could not be created. Check the selected course and values.',400)
        invalidate(app.config['REDIS_URL'],'emp:examinations'); return ok({'message':'Examination created'},201)
    @app.get('/api/examinations/<int:eid>')
    def exam_detail(eid):
        u,e=auth();
        if e:return e
        x=get_db().execute('SELECT x.*,c.name course_name,c.code course_code FROM examinations x JOIN courses c ON c.id=x.course_id WHERE x.id=?',(eid,)).fetchone()
        if not x:return fail('Examination not found',404)
        if u['role']=='examiner' and not get_db().execute('SELECT 1 FROM exam_assignments WHERE examination_id=? AND examiner_id=? UNION SELECT 1 FROM slots WHERE examination_id=? AND examiner_id=?',(eid,u['id'],eid,u['id'])).fetchone():return fail('Examination is not assigned to you',403)
        if u['role']=='student' and x['status'] not in ('Slot Creation','Booking Open'):return fail('Examination is not available',403)
        return ok({**dict(x),'rubrics':rows('SELECT * FROM rubrics WHERE examination_id=?',(eid,)),'slots':rows('SELECT s.*,u.name examiner FROM slots s JOIN users u ON u.id=s.examiner_id WHERE s.examination_id=?',(eid,))})
    @app.get('/api/student/examinations')
    def student_examinations():
        u,e=auth(['student'])
        if e:return e
        q=request.args.get('q','').strip(); typ=request.args.get('type'); params=[]; clauses=["x.status='Booking Open'"]
        if q:clauses.append('(x.name LIKE ? OR c.name LIKE ? OR c.code LIKE ?)'); params.extend([f'%{q}%',f'%{q}%',f'%{q}%'])
        if typ:clauses.append('x.type=?');params.append(typ)
        sql='SELECT x.*,c.code course_code,c.name course_name,COUNT(s.id) slot_count,COALESCE(SUM(CASE WHEN s.status="OPEN" THEN s.available ELSE 0 END),0) available_seats FROM examinations x JOIN courses c ON c.id=x.course_id LEFT JOIN slots s ON s.examination_id=x.id WHERE '+' AND '.join(clauses)+' GROUP BY x.id ORDER BY x.created_at DESC'
        return ok(rows(sql,params))
    @app.get('/api/student/upcoming')
    def student_upcoming():
        u,e=auth(['student'])
        if e:return e
        return ok(rows('SELECT b.*,x.name examination,c.name course,s.date,s.start_time,s.end_time,ex.name examiner FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=s.examiner_id WHERE b.student_id=? AND b.status="Booked" AND (s.date>date("now") OR (s.date=date("now") AND s.start_time>=time("now"))) ORDER BY s.date,s.start_time',(u['id'],)))
    @app.get('/api/student/history')
    def student_history():
        u,e=auth(['student'])
        if e:return e
        return ok(rows('SELECT b.*,x.name examination,c.name course,s.date,s.start_time,s.end_time,ex.name examiner,ev.total_marks FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=s.examiner_id LEFT JOIN evaluations ev ON ev.booking_id=b.id WHERE b.student_id=? ORDER BY s.date DESC,s.start_time DESC',(u['id'],)))
    @app.post('/api/rubrics')
    def rubric():
        u,e=auth(['admin']);
        if e:return e
        d=request.json or {}; db=get_db(); exam=db.execute('SELECT max_marks FROM examinations WHERE id=?',(d.get('examination_id'),)).fetchone()
        if not exam:return fail('Examination not found',404)
        current=db.execute('SELECT COALESCE(SUM(max_marks),0) total FROM rubrics WHERE examination_id=?',(d.get('examination_id'),)).fetchone()['total']
        if float(current)+float(d.get('max_marks',0))>float(exam['max_marks']):return fail('Rubric marks exceed examination maximum')
        db.execute('INSERT INTO rubrics(examination_id,criterion,max_marks,weightage,description) VALUES(?,?,?,?,?)',(d.get('examination_id'),d.get('criterion'),d.get('max_marks'),d.get('weightage',100),d.get('description',''))); db.commit(); invalidate(app.config['REDIS_URL'],f"emp:rubrics:{d.get('examination_id')}"); return ok({'message':'Rubric added'},201)
    @app.get('/api/users')
    def users():
        u,e=auth(['admin'])
        if e:return e
        role=request.args.get('role'); q=request.args.get('q','').strip(); clauses=["role!='admin'"]; params=[]
        if role in ('student','examiner'):clauses.append('role=?');params.append(role)
        if q:clauses.append('(name LIKE ? OR email LIKE ?)');params.extend([f'%{q}%',f'%{q}%'])
        return ok(rows('SELECT id,name,email,role,contact,department,status,created_at FROM users WHERE '+' AND '.join(clauses)+' ORDER BY name',params))
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
        if request.method=='GET':
            page,size,offset=paging(); clauses=[]; params=[]
            for key,column in [('examination_id','s.examination_id'),('examiner_id','s.examiner_id'),('date','s.date'),('status','s.status')]:
                if request.args.get(key): clauses.append(f'{column}=?'); params.append(request.args[key])
            where=(' WHERE '+' AND '.join(clauses)) if clauses else ''
            if not clauses and page==1 and size==50:
                data=get_json(app.config['REDIS_URL'],'emp:slots:v2')
                if data is None:
                    data=rows('SELECT s.*,x.name examination,x.status examination_status,u.name examiner FROM slots s JOIN examinations x ON x.id=s.examination_id JOIN users u ON u.id=s.examiner_id ORDER BY s.date,s.start_time'); set_json(app.config['REDIS_URL'],'emp:slots:v2',data,app.config['CACHE_TTL'])
                if u['role']=='examiner':data=[x for x in data if x['examiner_id']==u['id']]
                elif u['role']=='student':data=[x for x in data if x['examination_status']=='Booking Open' and x['status']=='OPEN']
                return ok(data)
            data=rows(f'SELECT s.*,x.name examination,x.status examination_status,u.name examiner FROM slots s JOIN examinations x ON x.id=s.examination_id JOIN users u ON u.id=s.examiner_id{where} ORDER BY s.date,s.start_time LIMIT ? OFFSET ?',params+[size,offset])
            if u['role']=='examiner':data=[x for x in data if x['examiner_id']==u['id']]
            elif u['role']=='student':data=[x for x in data if x['examination_status']=='Booking Open' and x['status']=='OPEN']
            return ok(data)
        if u['role'] not in ('admin','examiner'):return fail('Only examiners or admin can create slots',403)
        d=request.json or {}; exam_ref=str(d.get('examination_id','')).strip(); ex=db.execute('SELECT * FROM examinations WHERE CAST(id AS TEXT)=? OR name=?',(exam_ref,exam_ref)).fetchone()
        if not ex:return fail('Examination not found',404)
        eid=ex['id']
        if ex['status']!='Slot Creation':return fail('Slot creation is closed for this examination')
        now=datetime.now()
        for key,label in (('slot_start','slot creation'),('slot_end','slot creation') ):
            if ex[key]:
                try:
                    boundary=datetime.fromisoformat(ex[key].replace('Z','+00:00')).replace(tzinfo=None)
                    if (key=='slot_start' and now<boundary) or (key=='slot_end' and now>=boundary):return fail(f'Outside the configured {label} period')
                except ValueError:return fail('Examination timeline is invalid')
        examiner_id=u['id'] if u['role']=='examiner' else d.get('examiner_id')
        if u['role']=='admin' and not examiner_id:
            first_examiner=db.execute("SELECT id FROM users WHERE role='examiner' AND status='Active' ORDER BY id LIMIT 1").fetchone()
            examiner_id=first_examiner['id'] if first_examiner else None
        if not examiner_id:return fail('An active examiner must exist before creating a slot')
        candidate=db.execute("SELECT id FROM users WHERE id=? AND role='examiner' AND status='Active'",(examiner_id,)).fetchone()
        if not candidate:return fail('Active examiner not found',404)
        if u['role']=='examiner' and not db.execute('SELECT 1 FROM exam_assignments WHERE examination_id=? AND examiner_id=?',(eid,u['id'])).fetchone():return fail('You are not assigned to this examination',403)
        try:
            cap=int(d.get('capacity',1))
            start=datetime.strptime(d.get('start_time',''),'%H:%M').time()
            end=datetime.strptime(d.get('end_time',''),'%H:%M').time()
            datetime.strptime(d.get('date',''),'%Y-%m-%d')
            if cap<1 or start>=end:return fail('Provide a valid date, time range and positive capacity')
        except (TypeError,ValueError):return fail('Provide a valid date (YYYY-MM-DD), time (HH:MM) and positive capacity')
        overlap=db.execute("SELECT id FROM slots WHERE examiner_id=? AND date=? AND start_time<? AND end_time>? AND status<>'CANCELLED'",(examiner_id,d.get('date'),d.get('end_time'),d.get('start_time'))).fetchone()
        if overlap:return fail('Overlapping slot for examiner')
        db.execute('INSERT INTO slots(examination_id,examiner_id,date,start_time,end_time,capacity,available,meeting_link) VALUES(?,?,?,?,?,?,?,?)',(eid,examiner_id,d.get('date'),d.get('start_time'),d.get('end_time'),cap,cap,d.get('meeting_link'))); db.commit(); invalidate(app.config['REDIS_URL'],'emp:slots:v2'); return ok({'message':'Slot created'},201)
    @app.post('/api/bookings')
    def book():
        u,e=auth(['student']);
        if e:return e
        d=request.json or {}; db=get_db()
        try:
            db.execute('BEGIN IMMEDIATE'); s=db.execute('SELECT s.*,x.name,x.status exam_status,x.booking_start,x.booking_end FROM slots s JOIN examinations x ON x.id=s.examination_id WHERE s.id=?',(d.get('slot_id'),)).fetchone()
            if not s or s['available']<=0 or s['status']!='OPEN': raise ValueError('Slot is full or unavailable')
            if s['exam_status']!='Booking Open': raise ValueError('Booking is not open for this examination')
            now=datetime.now()
            for key in ('booking_start','booking_end'):
                if s[key]:
                    try:
                        boundary=datetime.fromisoformat(s[key].replace('Z','+00:00')).replace(tzinfo=None)
                        if (key=='booking_start' and now<boundary) or (key=='booking_end' and now>boundary): raise ValueError('Outside the configured booking period')
                    except ValueError as ex:
                        if str(ex)=='Outside the configured booking period':raise
                        raise ValueError('Examination timeline is invalid')
            if db.execute('SELECT b.id FROM bookings b JOIN slots z ON z.id=b.slot_id WHERE b.student_id=? AND z.examination_id=? AND b.status="Booked"',(u['id'],s['examination_id'])).fetchone(): raise ValueError('You already have a booking for this examination')
            db.execute('INSERT INTO bookings(student_id,slot_id) VALUES(?,?)',(u['id'],s['id']))
            booking_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]
            db.execute("INSERT INTO booking_history(booking_id,actor_user_id,action,new_slot_id) VALUES(?,?,'booked',?)",(booking_id,u['id'],s['id']))
            db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(u['id'],'Booking confirmed',f'Your booking for {s["name"]} on {s["date"]} at {s["start_time"]} is confirmed.'))
            db.execute('UPDATE slots SET available=available-1,status=CASE WHEN available-1=0 THEN "FULL" ELSE status END WHERE id=?',(s['id'],)); db.commit(); invalidate(app.config['REDIS_URL'],'emp:slots:v2'); return ok({'message':'Booking confirmed'},201)
        except ValueError as ex: db.rollback(); return fail(str(ex))
        except sqlite3.IntegrityError: db.rollback(); return fail('Duplicate booking',409)
    @app.get('/api/bookings')
    def bookings():
        u,e=auth();
        if e:return e
        q='SELECT b.*,x.name examination,x.max_marks,s.date,s.start_time,s.end_time,ex.name examiner,c.name course FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN users ex ON ex.id=s.examiner_id JOIN courses c ON c.id=x.course_id WHERE b.student_id=?' if u['role']=='student' else 'SELECT b.*,x.name examination,s.date,s.start_time,st.name student,ex.name examiner FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN users st ON st.id=b.student_id JOIN users ex ON ex.id=s.examiner_id WHERE '+('s.examiner_id=?' if u['role']=='examiner' else '1=1')
        params=list((u['id'],) if u['role']!='admin' else ()); filters=[]
        for key,column in [('status','b.status'),('date','s.date'),('exam_id','s.examination_id'),('examiner_id','s.examiner_id')]:
            if request.args.get(key):filters.append(f'{column}=?');params.append(request.args[key])
        if filters:q += ' AND ' + ' AND '.join(filters)
        page,size,offset=paging(); data=rows(q+' ORDER BY b.id DESC LIMIT ? OFFSET ?',params+[size,offset]); return ok(data)
    @app.get('/api/bookings/<int:bid>/history')
    def booking_history(bid):
        u,e=auth()
        if e:return e
        booking=get_db().execute('SELECT b.student_id,s.examiner_id FROM bookings b JOIN slots s ON s.id=b.slot_id WHERE b.id=?',(bid,)).fetchone()
        if not booking:return fail('Booking not found',404)
        if u['role']=='student' and booking['student_id']!=u['id']:return fail('Booking not found',404)
        if u['role']=='examiner' and booking['examiner_id']!=u['id']:return fail('Booking not found',404)
        return ok(rows('SELECT h.*,actor.name actor_name FROM booking_history h LEFT JOIN users actor ON actor.id=h.actor_user_id WHERE h.booking_id=? ORDER BY h.id',(bid,)))

    @app.post('/api/evaluations')
    def evaluate():
        u,e=auth(['examiner']);
        if e:return e
        d=request.json or {}; db=get_db(); b=db.execute('SELECT b.*,s.examiner_id,s.examination_id FROM bookings b JOIN slots s ON s.id=b.slot_id WHERE b.id=?',(d.get('booking_id'),)).fetchone()
        if not b or b['examiner_id']!=u['id']:return fail('Booking is not assigned to you',403)
        if b['status']!='Booked':return fail('Only active booked students can be evaluated')
        if db.execute('SELECT id FROM evaluations WHERE booking_id=?',(b['id'],)).fetchone():return fail('Evaluation already submitted',409)
        rub=rows('SELECT * FROM rubrics WHERE examination_id=?',(b['examination_id'],)); rubric_max={int(i['id']):float(i['max_marks']) for i in rub}; details=d.get('details',[])
        if len({int(i.get('rubric_id',0)) for i in details}) != len(details):return fail('Each rubric criterion may be entered only once')
        for item in details:
            try: awarded=float(item.get('marks',0)); rid=int(item.get('rubric_id'))
            except (TypeError,ValueError):return fail('Invalid rubric marks')
            if rid not in rubric_max or awarded<0 or awarded>rubric_max[rid]:return fail('Marks exceed a rubric criterion maximum')
        total=sum(float(i.get('marks',0)) for i in details); maxm=float(db.execute('SELECT max_marks FROM examinations WHERE id=?',(b['examination_id'],)).fetchone()['max_marks'])
        if total>maxm:return fail('Marks exceed examination maximum')
        db.execute('INSERT INTO evaluations(booking_id,student_id,examiner_id,total_marks,remarks) VALUES(?,?,?,?,?)',(b['id'],b['student_id'],u['id'],total,d.get('remarks',''))); eid=db.execute('SELECT last_insert_rowid()').fetchone()[0]
        for x in details: db.execute('INSERT INTO evaluation_details(evaluation_id,rubric_id,marks,comments) VALUES(?,?,?,?)',(eid,x['rubric_id'],x['marks'],x.get('comments','')))
        db.execute('UPDATE bookings SET status="Completed" WHERE id=?',(b['id'],)); db.commit(); return ok({'message':'Evaluation submitted'})

    @app.get('/api/evaluations/pending')
    def pending_evaluations():
        u,e=auth(['examiner']);
        if e:return e
        return ok(rows('SELECT b.id booking_id,st.name student,x.name examination,s.date,s.start_time FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN users st ON st.id=b.student_id LEFT JOIN evaluations ev ON ev.booking_id=b.id WHERE s.examiner_id=? AND b.status="Booked" AND ev.id IS NULL ORDER BY s.date,s.start_time',(u['id'],)))
    @app.get('/api/examiner/examinations')
    def examiner_examinations():
        u,e=auth(['examiner'])
        if e:return e
        return ok(rows('SELECT DISTINCT x.*,c.code course_code,c.name course_name FROM examinations x JOIN courses c ON c.id=x.course_id LEFT JOIN exam_assignments a ON a.examination_id=x.id LEFT JOIN slots s ON s.examination_id=x.id WHERE a.examiner_id=? OR s.examiner_id=? ORDER BY x.created_at DESC',(u['id'],u['id'])))

    @app.get('/api/evaluations/<int:booking_id>')
    def evaluation_form(booking_id):
        u,e=auth(['examiner']);
        if e:return e
        db=get_db(); b=db.execute('SELECT b.id booking_id,b.student_id,s.examiner_id,s.examination_id,st.name student,x.name examination FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN users st ON st.id=b.student_id JOIN examinations x ON x.id=s.examination_id WHERE b.id=?',(booking_id,)).fetchone()
        if not b or b['examiner_id']!=u['id']:return fail('Booking is not assigned to you',403)
        return ok({**dict(b),'rubrics':rows('SELECT * FROM rubrics WHERE examination_id=? ORDER BY id',(b['examination_id'],))})
    @app.get('/api/results')
    def results():
        u,e=auth()
        if e:return e
        base='SELECT ev.*,x.name examination,c.name course,ex.name examiner FROM evaluations ev JOIN bookings b ON b.id=ev.booking_id JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=ev.examiner_id'
        if u['role']=='student':return ok(rows(base+' WHERE x.published=1 AND b.student_id=?',(u['id'],)))
        if u['role']=='examiner':return ok(rows(base+' WHERE ev.examiner_id=?',(u['id'],)))
        return ok(rows(base))
    @app.get('/api/results/<int:evaluation_id>')
    def result_detail(evaluation_id):
        u,e=auth()
        if e:return e
        db=get_db(); ev=db.execute('SELECT ev.*,b.student_id,x.name examination,x.max_marks,c.name course,x.published,ex.name examiner FROM evaluations ev JOIN bookings b ON b.id=ev.booking_id JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=ev.examiner_id WHERE ev.id=?',(evaluation_id,)).fetchone()
        if not ev:return fail('Result not found',404)
        if u['role']=='student' and (ev['student_id']!=u['id'] or not ev['published']):return fail('Result is not available',403)
        if u['role']=='examiner' and ev['examiner_id']!=u['id']:return fail('Forbidden',403)
        details=rows('SELECT d.*,r.criterion,r.max_marks rubric_max FROM evaluation_details d JOIN rubrics r ON r.id=d.rubric_id WHERE d.evaluation_id=?',(evaluation_id,))
        return ok({**dict(ev),'details':details})
    @app.get('/api/scorecards/<int:evaluation_id>')
    def scorecard(evaluation_id):
        u,e=auth(['student'])
        if e:return e
        db=get_db(); ev=db.execute('SELECT ev.*,b.student_id,x.name examination,x.max_marks,c.name course,ex.name examiner,x.published FROM evaluations ev JOIN bookings b ON b.id=ev.booking_id JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=ev.examiner_id WHERE ev.id=?',(evaluation_id,)).fetchone()
        if not ev or ev['student_id']!=u['id'] or not ev['published']:return fail('Scorecard is not available',404)
        details=rows('SELECT r.criterion,r.max_marks,d.marks,d.comments FROM evaluation_details d JOIN rubrics r ON r.id=d.rubric_id WHERE d.evaluation_id=?',(evaluation_id,))
        table=''.join(f'<tr><td>{d["criterion"]}</td><td>{d["marks"]}/{d["max_marks"]}</td><td>{d["comments"] or ""}</td></tr>' for d in details)
        html=f'<html><body><h1>EMP Scorecard</h1><p><b>{ev["examination"]}</b> — {ev["course"]}</p><p>Examiner: {ev["examiner"]}</p><h2>{ev["total_marks"]}/{ev["max_marks"]}</h2><p>{ev["remarks"] or ""}</p><table border="1" cellpadding="6"><tr><th>Criterion</th><th>Marks</th><th>Comments</th></tr>{table}</table></body></html>'
        return Response(html,mimetype='text/html',headers={'Content-Disposition':'attachment; filename=scorecard.html'})
    @app.post('/api/examinations/<int:eid>/publish')
    def publish(eid):
        u,e=auth(['admin']);
        if e:return e
        db=get_db(); db.execute('UPDATE examinations SET published=1,status="Completed" WHERE id=?',(eid,)); students=db.execute('SELECT DISTINCT b.student_id,x.name FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN evaluations ev ON ev.booking_id=b.id WHERE x.id=?',(eid,)).fetchall(); db.executemany('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',[(r['student_id'],'Result published',f'Results for {r["name"]} are now available.') for r in students]); db.commit(); return ok({'message':'Results published','notified':len(students)})
    @app.post('/api/examinations/<int:eid>/complete')
    def examiner_complete_exam(eid):
        u,e=auth(['examiner'])
        if e:return e
        db=get_db(); assigned=db.execute('SELECT 1 FROM slots WHERE examination_id=? AND examiner_id=? UNION SELECT 1 FROM exam_assignments WHERE examination_id=? AND examiner_id=?',(eid,u['id'],eid,u['id'])).fetchone()
        if not assigned:return fail('Examination is not assigned to you',403)
        db.execute('UPDATE examinations SET status="Completed" WHERE id=?',(eid,)); db.execute('INSERT INTO audit_log(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)',(u['id'],'complete','examination',eid,'Marked completed by examiner')); db.commit(); invalidate(app.config['REDIS_URL'],'emp:examinations'); return ok({'message':'Examination marked completed'})
    @app.get('/api/export.csv')
    def export_csv():
        u,e=auth(['student']);
        if e:return e
        data=rows('SELECT x.name examination,c.name course,s.date,ex.name examiner,COALESCE(ev.total_marks,"") marks,b.status FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id JOIN courses c ON c.id=x.course_id JOIN users ex ON ex.id=s.examiner_id LEFT JOIN evaluations ev ON ev.booking_id=b.id WHERE b.student_id=?',(u['id'],)); out=io.StringIO(); w=csv.DictWriter(out,fieldnames=['examination','course','date','examiner','marks','status']); w.writeheader(); w.writerows(data); return send_file(io.BytesIO(out.getvalue().encode()),as_attachment=True,download_name='examination-history.csv',mimetype='text/csv')

    @app.post('/api/exports')
    def start_export():
        u,e=auth(['student']);
        if e:return e
        db=get_db(); db.execute('INSERT INTO jobs(user_id,type,status) VALUES(?,?,?)',(u['id'],'student_history_csv','Queued')); job_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]; db.commit()
        try:
            from tasks.scheduled_tasks import student_history_export
            student_history_export.delay(u['id'],job_id)
        except Exception:
            db.execute('UPDATE jobs SET status="Unavailable" WHERE id=?',(job_id,)); db.commit()
        return ok({'job_id':job_id,'status':'Queued'},202)

    @app.get('/api/exports/<int:job_id>')
    def export_status(job_id):
        u,e=auth(['student']);
        if e:return e
        j=get_db().execute('SELECT * FROM jobs WHERE id=? AND user_id=?',(job_id,u['id'])).fetchone()
        if not j:return fail('Export job not found',404)
        if j['status']!='Completed':return ok(dict(j))
        return ok({**dict(j),'download_url':f'/api/exports/{job_id}/download'})

    @app.get('/api/exports/<int:job_id>/download')
    def export_download(job_id):
        u,e=auth(['student']);
        if e:return e
        j=get_db().execute('SELECT * FROM jobs WHERE id=? AND user_id=? AND status="Completed"',(job_id,u['id'])).fetchone()
        if not j or not j['filename'] or not os.path.exists(j['filename']):return fail('Export is not ready',404)
        return send_file(j['filename'],as_attachment=True,download_name='examination-history.csv',mimetype='text/csv')

    @app.route('/api/courses/<int:cid>', methods=['PUT','DELETE'])
    def course_detail(cid):
        u,e=auth(['admin']);
        if e:return e
        db=get_db();
        if not db.execute('SELECT id FROM courses WHERE id=?',(cid,)).fetchone(): return fail('Course not found',404)
        if request.method=='DELETE': db.execute('UPDATE courses SET status="Inactive" WHERE id=?',(cid,)); db.commit(); invalidate(app.config['REDIS_URL'],'emp:examinations'); return ok({'message':'Course deactivated'})
        d=request.json or {}; db.execute('UPDATE courses SET code=COALESCE(?,code),name=COALESCE(?,name),description=COALESCE(?,description),status=COALESCE(?,status) WHERE id=?',(d.get('code'),d.get('name'),d.get('description'),d.get('status'),cid)); db.commit(); invalidate(app.config['REDIS_URL'],'emp:examinations'); return ok({'message':'Course updated'})

    @app.get('/api/examiners')
    def examiners():
        u,e=auth(['admin']); return e or ok(rows("SELECT u.id,u.name,u.email,u.contact,u.department,u.status,COUNT(s.id) slot_count FROM users u LEFT JOIN slots s ON s.examiner_id=u.id WHERE u.role='examiner' GROUP BY u.id ORDER BY u.name"))

    @app.post('/api/examinations/<int:eid>/assign')
    def assign_examiner(eid):
        u,e=auth(['admin']);
        if e:return e
        examiner_id=(request.json or {}).get('examiner_id'); db=get_db()
        if not db.execute('SELECT id FROM examinations WHERE id=?',(eid,)).fetchone():return fail('Examination not found',404)
        if not db.execute("SELECT id FROM users WHERE id=? AND role='examiner' AND status='Active'",(examiner_id,)).fetchone():return fail('Active examiner not found',404)
        try: db.execute('INSERT INTO exam_assignments(examination_id,examiner_id) VALUES(?,?)',(eid,examiner_id)); db.commit()
        except sqlite3.IntegrityError: return fail('Examiner is already assigned',409)
        return ok({'message':'Examiner assigned'})

    @app.put('/api/bookings/<int:bid>/reschedule')
    def reschedule_booking(bid):
        u,e=auth(['admin']);
        if e:return e
        new_slot=(request.json or {}).get('slot_id'); db=get_db()
        try:
            db.execute('BEGIN IMMEDIATE'); booking=db.execute('SELECT b.*,old.examination_id FROM bookings b JOIN slots old ON old.id=b.slot_id WHERE b.id=?',(bid,)).fetchone(); slot=db.execute('SELECT * FROM slots WHERE id=?',(new_slot,)).fetchone()
            if not booking or not slot:return fail('Booking or target slot not found',404)
            if booking['status']!='Booked':return fail('Only active bookings can be rescheduled')
            if slot['id']==booking['slot_id']:return fail('Choose a different slot')
            if slot['examination_id']!=booking['examination_id']:return fail('A booking can only be moved within the same examination')
            if slot['available']<1 or slot['status']!='OPEN':return fail('Target slot is unavailable')
            if db.execute('SELECT 1 FROM bookings b JOIN slots z ON z.id=b.slot_id WHERE b.student_id=? AND z.examination_id=? AND b.status="Booked" AND b.id<>?',(booking['student_id'],booking['examination_id'],bid)).fetchone():return fail('Student already has an active booking for this examination')
            if db.execute('SELECT 1 FROM bookings WHERE student_id=? AND slot_id=? AND status="Booked"',(booking['student_id'],new_slot)).fetchone():return fail('Student already has a booking in the target slot')
            db.execute('UPDATE bookings SET slot_id=? WHERE id=?',(new_slot,bid))
            db.execute("INSERT INTO booking_history(booking_id,actor_user_id,action,old_slot_id,new_slot_id) VALUES(?,?,'rescheduled',?,?)",(bid,u['id'],booking['slot_id'],new_slot))
            db.execute('UPDATE slots SET available=MIN(capacity,available+1),status="OPEN" WHERE id=?',(booking['slot_id'],)); db.execute('UPDATE slots SET available=available-1,status=CASE WHEN available-1=0 THEN "FULL" ELSE status END WHERE id=?',(new_slot,)); db.execute('INSERT INTO audit_log(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)',(u['id'],'reschedule','booking',bid,f'old_slot={booking["slot_id"]};new_slot={new_slot}')); db.commit(); invalidate(app.config['REDIS_URL'],'emp:slots:v2'); return ok({'message':'Booking rescheduled'})
        except Exception:
            db.rollback(); raise

    @app.put('/api/users/<int:uid>')
    def user_update(uid):
        u,e=auth(['admin']);
        if e:return e
        d=request.json or {}; db=get_db()
        target=db.execute('SELECT role FROM users WHERE id=? AND role<>"admin"',(uid,)).fetchone()
        if not target:return fail('User not found',404)
        if d.get('status') not in (None,'Active','Inactive'):return fail('Status must be Active or Inactive')
        db.execute('UPDATE users SET name=COALESCE(?,name),contact=COALESCE(?,contact),department=COALESCE(?,department),status=COALESCE(?,status) WHERE id=? AND role<>"admin"',(d.get('name'),d.get('contact'),d.get('department'),d.get('status'),uid)); db.commit(); return ok({'message':'User updated'})

    @app.get('/api/notifications')
    def notifications():
        u,e=auth(); return e or ok(rows('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC',(u['id'],)))
    @app.post('/api/notifications/<int:nid>/read')
    def notification_read(nid):
        u,e=auth()
        if e:return e
        db=get_db(); db.execute('UPDATE notifications SET read=1 WHERE id=? AND user_id=?',(nid,u['id'])); db.commit(); return ok({'message':'Notification marked read'})

    @app.put('/api/profile')
    def profile_update():
        u,e=auth()
        if e:return e
        d=request.json or {}; db=get_db(); db.execute('UPDATE users SET name=COALESCE(?,name),contact=COALESCE(?,contact) WHERE id=?',(d.get('name'),d.get('contact'),u['id'])); db.commit(); return ok({'message':'Profile updated'})

    @app.post('/api/profile/password')
    def password_change():
        u,e=auth()
        if e:return e
        d=request.json or {}
        if not check_password_hash(u['password_hash'],d.get('current_password','')):return fail('Current password is incorrect',403)
        if len(d.get('new_password',''))<6:return fail('New password must contain at least 6 characters')
        db=get_db(); db.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(d['new_password']),u['id'])); db.commit(); return ok({'message':'Password changed'})

    @app.post('/api/bookings/<int:bid>/cancel')
    def cancel_booking(bid):
        u,e=auth(['student','admin']);
        if e:return e
        db=get_db(); b=db.execute('SELECT b.*,s.available,s.capacity,s.status slot_status,x.booking_end FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN examinations x ON x.id=s.examination_id WHERE b.id=?',(bid,)).fetchone()
        if not b or (u['role']=='student' and b['student_id']!=u['id']): return fail('Booking not found',404)
        if b['status']!='Booked': return fail('Only active bookings can be cancelled')
        if u['role']=='student' and b['booking_end']:
            try:
                if datetime.now()>=datetime.fromisoformat(b['booking_end'].replace('Z','+00:00')).replace(tzinfo=None):return fail('Booking cancellation deadline has passed')
            except ValueError:return fail('Examination timeline is invalid')
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT status FROM bookings WHERE id=?',(bid,)).fetchone()
        if not current or current['status']!='Booked':db.rollback(); return fail('Only active bookings can be cancelled')
        db.execute('UPDATE bookings SET status="Cancelled" WHERE id=?',(bid,))
        db.execute("INSERT INTO booking_history(booking_id,actor_user_id,action,old_slot_id) VALUES(?,?,'cancelled',?)",(bid,u['id'],b['slot_id']))
        db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(b['student_id'],'Booking cancelled','Your examination booking has been cancelled.'))
        db.execute('UPDATE slots SET available=MIN(capacity,available+1),status="OPEN" WHERE id=?',(b['slot_id'],)); db.commit(); invalidate(app.config['REDIS_URL'],'emp:slots:v2'); return ok({'message':'Booking cancelled'})

    @app.get('/api/reports/summary')
    def report_summary():
        u,e=auth(['admin']);
        if e:return e
        db=get_db(); return ok({'by_status':rows('SELECT status,COUNT(*) count FROM bookings GROUP BY status'),'by_exam':rows('SELECT x.name,COUNT(b.id) bookings,COUNT(ev.id) evaluations FROM examinations x LEFT JOIN slots s ON s.examination_id=x.id LEFT JOIN bookings b ON b.slot_id=s.id LEFT JOIN evaluations ev ON ev.booking_id=b.id GROUP BY x.id'),'examiner_workload':rows("SELECT u.name,COUNT(b.id) bookings,COUNT(ev.id) completed FROM users u LEFT JOIN slots s ON s.examiner_id=u.id LEFT JOIN bookings b ON b.slot_id=s.id LEFT JOIN evaluations ev ON ev.booking_id=b.id WHERE u.role='examiner' GROUP BY u.id ORDER BY bookings DESC")})

    @app.get('/api/reports/monthly/download')
    def monthly_report_download():
        u,e=auth(['admin']);
        if e:return e
        path=os.path.join(app.root_path,'instance','monthly_report.html')
        if not os.path.exists(path):return fail('No monthly report has been generated yet',404)
        return send_file(path,as_attachment=True,download_name='monthly-examination-report.html',mimetype='text/html')

    @app.post('/api/reports/monthly/generate')
    def generate_monthly_report():
        u,e=auth(['admin']);
        if e:return e
        try:
            from tasks.scheduled_tasks import monthly_report
            result=monthly_report.delay()
            return ok({'status':'Queued','task_id':result.id},202)
        except Exception as exc:
            return fail('Celery is unavailable; start Redis and a worker before generating reports')

    @app.get('/api/rubrics/<int:eid>')
    def rubrics(eid):
        u,e=auth()
        if e:return e
        if u['role']=='student':return fail('Rubrics are available to examiners and Admin only',403)
        if u['role']=='examiner' and not get_db().execute('SELECT 1 FROM exam_assignments WHERE examination_id=? AND examiner_id=? UNION SELECT 1 FROM slots WHERE examination_id=? AND examiner_id=?',(eid,u['id'],eid,u['id'])).fetchone():return fail('Examination is not assigned to you',403)
        key=f'emp:rubrics:{eid}'; data=get_json(app.config['REDIS_URL'],key)
        if data is None:data=rows('SELECT * FROM rubrics WHERE examination_id=? ORDER BY id',(eid,)); set_json(app.config['REDIS_URL'],key,data,app.config['CACHE_TTL'])
        return ok(data)

    @app.route('/api/rubrics/<int:rid>', methods=['PUT','DELETE'])
    def rubric_detail(rid):
        u,e=auth(['admin']);
        if e:return e
        db=get_db()
        rubric_row=db.execute('SELECT examination_id FROM rubrics WHERE id=?',(rid,)).fetchone()
        if not rubric_row:return fail('Rubric not found',404)
        if request.method=='DELETE': db.execute('DELETE FROM rubrics WHERE id=?',(rid,))
        else:
            d=request.json or {}; existing=db.execute('SELECT max_marks FROM rubrics WHERE id=?',(rid,)).fetchone(); exam=db.execute('SELECT max_marks FROM examinations WHERE id=?',(rubric_row['examination_id'],)).fetchone(); proposed=float(d.get('max_marks',existing['max_marks'])); other=db.execute('SELECT COALESCE(SUM(max_marks),0) total FROM rubrics WHERE examination_id=? AND id<>?',(rubric_row['examination_id'],rid)).fetchone()['total']
            if proposed<0 or float(other)+proposed>float(exam['max_marks']):return fail('Rubric marks exceed examination maximum')
            db.execute('UPDATE rubrics SET criterion=COALESCE(?,criterion),max_marks=COALESCE(?,max_marks),weightage=COALESCE(?,weightage),description=COALESCE(?,description) WHERE id=?',(d.get('criterion'),d.get('max_marks'),d.get('weightage'),d.get('description'),rid))
        db.commit(); invalidate(app.config['REDIS_URL'],f"emp:rubrics:{rubric_row['examination_id']}"); return ok({'message':'Rubric updated'})

    @app.route('/api/examinations/<int:eid>', methods=['PUT','DELETE'])
    def examination_update(eid):
        u,e=auth(['admin']);
        if e:return e
        db=get_db()
        if request.method=='DELETE': db.execute('UPDATE examinations SET status="Closed" WHERE id=?',(eid,)); db.commit(); invalidate(app.config['REDIS_URL'],'emp:examinations'); return ok({'message':'Examination closed'})
        d=request.json or {}
        if d.get('status') not in (None,'Draft','Slot Creation','Booking Open','Closed','Completed'):return fail('Invalid examination status')
        if d.get('type') not in (None,'Viva','Practical','Project Demo','Assessment'):return fail('Unsupported examination type')
        try:
            if d.get('duration') is not None and int(d['duration'])<=0:return fail('Duration must be positive')
            if d.get('max_marks') is not None and float(d['max_marks'])<=0:return fail('Maximum marks must be positive')
            timeline={key:d.get(key) for key in ('slot_start','slot_end','booking_start','booking_end') if d.get(key)}
            parsed={key:datetime.fromisoformat(value.replace('Z','+00:00')).replace(tzinfo=None) for key,value in timeline.items()}
            if 'slot_start' in parsed and 'slot_end' in parsed and parsed['slot_start']>parsed['slot_end']:return fail('Slot creation timeline is inconsistent')
            if 'booking_start' in parsed and 'booking_end' in parsed and parsed['booking_start']>parsed['booking_end']:return fail('Booking timeline is inconsistent')
        except (TypeError,ValueError):return fail('Invalid duration, maximum marks or timeline value')
        db.execute('UPDATE examinations SET name=COALESCE(?,name),type=COALESCE(?,type),duration=COALESCE(?,duration),max_marks=COALESCE(?,max_marks),status=COALESCE(?,status),instructions=COALESCE(?,instructions),published=COALESCE(?,published),slot_start=COALESCE(?,slot_start),slot_end=COALESCE(?,slot_end),booking_start=COALESCE(?,booking_start),booking_end=COALESCE(?,booking_end) WHERE id=?',(d.get('name'),d.get('type'),d.get('duration'),d.get('max_marks'),d.get('status'),d.get('instructions'),d.get('published'),d.get('slot_start'),d.get('slot_end'),d.get('booking_start'),d.get('booking_end'),eid)); db.commit(); invalidate(app.config['REDIS_URL'],'emp:examinations'); return ok({'message':'Examination updated'})

    @app.route('/api/slots/<int:sid>', methods=['PUT','DELETE'])
    def slot_delete(sid):
        u,e=auth(['admin','examiner']);
        if e:return e
        db=get_db(); s=db.execute('SELECT * FROM slots WHERE id=?',(sid,)).fetchone()
        if not s or (u['role']=='examiner' and s['examiner_id']!=u['id']):return fail('Slot not found',404)
        active_bookings=db.execute('SELECT id,student_id FROM bookings WHERE slot_id=? AND status="Booked"',(sid,)).fetchall()
        if active_bookings and request.method=='DELETE':return fail('Slots with active bookings cannot be cancelled')
        exam=db.execute('SELECT booking_start,slot_start,slot_end,status FROM examinations WHERE id=?',(s['examination_id'],)).fetchone()
        if u['role']=='examiner':
            if exam and exam['status']=='Booking Open':return fail('Slots cannot be changed after student booking opens')
            if exam and exam['booking_start']:
                try:
                    if datetime.now()>=datetime.fromisoformat(exam['booking_start'].replace('Z','+00:00')).replace(tzinfo=None):return fail('Slots cannot be changed after booking begins')
                except ValueError:return fail('Examination timeline is invalid')
        if request.method=='PUT':
            d=request.json or {}
            if active_bookings and (u['role']!='admin' or any(d.get(field) is not None for field in ('date','start_time','end_time','capacity'))):return fail('Only Admin may reassign an examiner on a booked slot; booked times and capacity cannot be changed')
            if u['role']=='examiner' and exam and exam['slot_end']:
                try:
                    if datetime.now()>=datetime.fromisoformat(exam['slot_end'].replace('Z','+00:00')).replace(tzinfo=None):return fail('Slot creation period has ended')
                except ValueError:return fail('Examination timeline is invalid')
            booked_count=len(active_bookings)
            try:
                new_capacity=int(d.get('capacity',s['capacity']))
                new_date=d.get('date') or s['date']; new_start=d.get('start_time') or s['start_time']; new_end=d.get('end_time') or s['end_time']
                datetime.strptime(new_date,'%Y-%m-%d')
                if new_capacity<booked_count or new_capacity<1 or datetime.strptime(new_start,'%H:%M').time()>=datetime.strptime(new_end,'%H:%M').time():return fail('Capacity and time range are invalid or below existing bookings')
            except (TypeError,ValueError):return fail('Provide a valid date, time range and capacity')
            examiner_for_overlap=d.get('examiner_id',s['examiner_id'])
            if db.execute("SELECT id FROM slots WHERE id<>? AND examiner_id=? AND date=? AND start_time<? AND end_time>? AND status<>'CANCELLED'",(sid,examiner_for_overlap,new_date,new_end,new_start)).fetchone():return fail('Overlapping slot for examiner')
            examiner_id=s['examiner_id']
            if d.get('examiner_id') is not None:
                if u['role']!='admin':return fail('Only Admin can reassign an examiner',403)
                candidate=db.execute("SELECT id FROM users WHERE id=? AND role='examiner' AND status='Active'",(d['examiner_id'],)).fetchone()
                if not candidate:return fail('Active examiner not found',404)
                examiner_id=candidate['id']
                db.execute('INSERT OR IGNORE INTO exam_assignments(examination_id,examiner_id) VALUES(?,?)',(s['examination_id'],examiner_id))
                db.execute('INSERT INTO audit_log(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)',(u['id'],'reassign_examiner','slot',sid,f'examiner_id={examiner_id}'))
                for booking in active_bookings:
                    db.execute("INSERT INTO booking_history(booking_id,actor_user_id,action,old_slot_id,new_slot_id,details) VALUES(?,?,'examiner_reassigned',?,?,?)",(booking['id'],u['id'],sid,sid,f'examiner_id={examiner_id}'))
                    db.execute('INSERT INTO notifications(user_id,title,message) VALUES(?,?,?)',(booking['student_id'],'Examiner reassigned','Your examination examiner has been updated by Admin.'))
            db.execute('UPDATE slots SET examiner_id=?,date=?,start_time=?,end_time=?,capacity=?,available=?,status=CASE WHEN ?=0 THEN "FULL" ELSE "OPEN" END,meeting_link=COALESCE(?,meeting_link) WHERE id=?',(examiner_id,new_date,new_start,new_end,new_capacity,new_capacity-booked_count,new_capacity-booked_count,d.get('meeting_link'),sid)); db.commit(); invalidate(app.config['REDIS_URL'],'emp:slots:v2'); return ok({'message':'Slot updated'})
        db.execute("UPDATE slots SET status='CANCELLED',available=0 WHERE id=?",(sid,)); db.commit(); invalidate(app.config['REDIS_URL'],'emp:slots:v2'); return ok({'message':'Slot cancelled'})
    return app
