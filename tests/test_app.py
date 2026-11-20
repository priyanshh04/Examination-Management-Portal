import os, tempfile, unittest
from app_factory import create_app
from config import Config
class PortalTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.NamedTemporaryFile(delete=False); self.tmp.close(); Config.DATABASE=self.tmp.name; self.app=create_app(); self.app.config.update(TESTING=True,SECRET_KEY='test'); self.c=self.app.test_client()
 def tearDown(self): os.unlink(self.tmp.name)
 def test_admin_login_and_student_register(self):
  r=self.c.post('/api/auth/login',json={'email':'admin@emp.local','password':'Admin@123'}); self.assertEqual(r.status_code,200)
  self.assertEqual(self.c.post('/api/examinations',json={'course_id':9999,'name':'Invalid','type':'Viva','duration':30,'max_marks':100}).status_code,400)
  self.assertIn(b'Admin credentials come from your .env file.',self.c.get('/').data)
  self.c.post('/api/auth/logout'); r=self.c.post('/api/auth/register',json={'name':'S','email':'s@test.local','password':'secret1'}); self.assertEqual(r.status_code,201)
 def test_booking_cancellation_and_evaluation_workflow(self):
  self.assertEqual(self.c.post('/api/auth/login',json={'email':'admin@emp.local','password':'Admin@123'}).status_code,200)
  course=self.c.post('/api/courses',json={'code':'CS101','name':'Computer Science'}).get_json()['data']
  courses=self.c.get('/api/courses').get_json()['data']; course_id=next(x['id'] for x in courses if x['code']=='CS101')
  self.c.post('/api/examinations',json={'course_id':'CS101','name':'Oral Exam','type':'Viva','duration':30,'max_marks':100,'status':'Slot Creation'})
  exam_id=self.c.get('/api/examinations').get_json()['data'][0]['id']
  self.assertEqual(self.c.post('/api/rubrics',json={'examination_id':exam_id,'criterion':'Knowledge','max_marks':100}).status_code,201)
  rubric_id=self.c.get(f'/api/rubrics/{exam_id}').get_json()['data'][0]['id']; self.assertEqual(self.c.put(f'/api/rubrics/{rubric_id}',json={'max_marks':101}).status_code,400)
  self.assertEqual(self.c.post('/api/examiners',json={'name':'Examiner','email':'examiner@test.local','password':'secret1'}).status_code,201)
  examiner_id=self.c.get('/api/examiners').get_json()['data'][0]['id']
  self.assertEqual(self.c.post(f'/api/examinations/{exam_id}/assign',json={'examiner_id':examiner_id}).status_code,200)
  self.c.post('/api/auth/logout'); self.assertEqual(self.c.post('/api/auth/login',json={'email':'examiner@test.local','password':'secret1'}).status_code,200)
  self.assertEqual(self.c.post('/api/slots',json={'examination_id':'Oral Exam','date':'2099-01-01','start_time':'10:00','end_time':'10:30','capacity':1}).status_code,201)
  slot_id=self.c.get('/api/slots').get_json()['data'][0]['id']
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/login',json={'email':'admin@emp.local','password':'Admin@123'})
  self.assertEqual(self.c.put(f'/api/examinations/{exam_id}',json={'status':'Booking Open'}).status_code,200)
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/register',json={'name':'Student','email':'student@test.local','password':'secret1'}); self.c.post('/api/auth/login',json={'email':'student@test.local','password':'secret1'})
  self.assertEqual(self.c.post('/api/bookings',json={'slot_id':slot_id}).status_code,201)
  self.assertEqual(self.c.post('/api/bookings',json={'slot_id':slot_id}).status_code,400)
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/register',json={'name':'Second Student','email':'student2@test.local','password':'secret1'}); self.c.post('/api/auth/login',json={'email':'student2@test.local','password':'secret1'})
  self.assertEqual(self.c.post('/api/courses',json={'code':'NOPE','name':'Denied'}).status_code,403)
  self.assertEqual(self.c.post('/api/bookings',json={'slot_id':slot_id}).status_code,400)
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/login',json={'email':'student@test.local','password':'secret1'})
  booking_id=self.c.get('/api/bookings').get_json()['data'][0]['id']
  self.assertEqual(self.c.get(f'/api/bookings/{booking_id}/history').status_code,200)
  self.assertEqual(self.c.post(f'/api/bookings/{booking_id}/cancel').status_code,200)
  self.assertEqual(self.c.post('/api/bookings',json={'slot_id':slot_id}).status_code,201)
  booking_id=self.c.get('/api/bookings').get_json()['data'][0]['id']
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/login',json={'email':'examiner@test.local','password':'secret1'})
  rubric_id=self.c.get(f'/api/rubrics/{exam_id}').get_json()['data'][0]['id']
  self.assertEqual(self.c.post('/api/evaluations',json={'booking_id':booking_id,'details':[{'rubric_id':rubric_id,'marks':88}],'remarks':'Good performance'}).status_code,200)
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/login',json={'email':'admin@emp.local','password':'Admin@123'}); self.assertEqual(self.c.post(f'/api/examinations/{exam_id}/publish').status_code,200)
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/login',json={'email':'student@test.local','password':'secret1'}); results=self.c.get('/api/results').get_json()['data']; self.assertEqual(results[0]['total_marks'],88); self.assertEqual(self.c.get('/api/results/'+str(results[0]['id'])).status_code,200); self.assertEqual(self.c.get('/api/scorecards/'+str(results[0]['id'])).status_code,200); self.assertEqual(self.c.get('/api/student/history').status_code,200); self.assertEqual(self.c.get('/api/student/examinations').status_code,200); self.assertEqual(self.c.get('/api/export.csv').status_code,200)
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/login',json={'email':'examiner@test.local','password':'secret1'}); self.assertTrue(self.c.get('/api/examiner/examinations').get_json()['data'])
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/login',json={'email':'student@test.local','password':'secret1'})
  os.environ['EMP_DATABASE']=self.tmp.name; os.environ['CELERY_TASK_ALWAYS_EAGER']='1'; export=self.c.post('/api/exports'); self.assertEqual(export.status_code,202); job=self.c.get('/api/exports/'+str(export.get_json()['data']['job_id'])).get_json()['data']; self.assertEqual(job['status'],'Completed')
  self.c.post('/api/auth/logout'); self.c.post('/api/auth/login',json={'email':'admin@emp.local','password':'Admin@123'}); self.assertTrue(self.c.get('/api/bookings').get_json()['data']); stats=self.c.get('/api/dashboard').get_json()['data']; self.assertEqual(stats['courses'],1); self.assertEqual(stats['examinations'],1); self.assertGreaterEqual(stats['students'],2); self.assertEqual(stats['bookings'],2)
if __name__=='__main__': unittest.main()
