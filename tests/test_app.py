import os, tempfile, unittest
from app_factory import create_app
class PortalTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.NamedTemporaryFile(delete=False); self.tmp.close(); self.app=create_app(); self.app.config.update(TESTING=True,DATABASE=self.tmp.name,SECRET_KEY='test'); self.c=self.app.test_client()
 def tearDown(self): os.unlink(self.tmp.name)
 def test_admin_login_and_student_register(self):
  r=self.c.post('/api/auth/login',json={'email':'admin@emp.local','password':'Admin@123'}); self.assertEqual(r.status_code,200)
  self.c.post('/api/auth/logout'); r=self.c.post('/api/auth/register',json={'name':'S','email':'s@test.local','password':'secret1'}); self.assertEqual(r.status_code,201)
if __name__=='__main__': unittest.main()
