"""Security and tenant-boundary regression tests for the web entry point."""
import base64,concurrent.futures,io,json,sqlite3,tempfile,unittest,shutil
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import core,pyotp
from web_auth import Auth,AuthError
from web_server import WebApp

PASSWORD='Password-iniziale-test-2026!'
PERSONAL='Password-personale-test-2026!'

class Client:
    def __init__(self,application):self.app=application;self.cookie='';self.csrf='';self.headers={}
    def call(self,path,body=None,**overrides):
        path,_,query=path.partition('?');raw=json.dumps(body).encode() if body is not None else b''
        env={'REQUEST_METHOD':'POST' if body is not None else 'GET','PATH_INFO':path,'QUERY_STRING':query,'HTTP_HOST':self.app.host,'HTTP_ORIGIN':self.app.origin,'REMOTE_ADDR':'127.0.0.1','HTTP_COOKIE':self.cookie,'HTTP_X_PRESENZE_TOKEN':self.csrf,'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw)};env.update(overrides)
        status=[]
        def start(s,h):status.append(int(s.split()[0]));self.headers=dict(h)
        raw=b''.join(self.app(env,start))
        if 'Set-Cookie' in self.headers:self.cookie=self.headers['Set-Cookie'].split(';')[0]
        result=json.loads(raw) if self.headers['Content-Type'].startswith('application/json') else raw
        if isinstance(result,dict) and 'csrf' in result:self.csrf=result['csrf']
        return status[0],result
    def ok(self,path,body=None):
        status,out=self.call(path,body)
        if status!=200:raise AssertionError((path,status,out))
        return out

class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old_db=core.DB;self.old_revoke=core.revoke
        self.key=self.root/'private/key';Auth.create_key(self.key)
        self.web=WebApp(self.root/'data',self.key,'https://presenze.test');self.clock=1_790_000_000
        self.web.auth.clock=lambda:self.clock
        core.setup(dict(username='admin',name='Admin demo',center_name='Centro A',password=PASSWORD))
        with core.connect() as c:
            row=c.execute('SELECT * FROM users').fetchone();self.uid=row['id'];self.admin=core.public_user(row);self.cid=core.centers_for(c,self.admin)[0]['id']
        self.activation=self.web.auth.activation(self.uid,{'username':'console'},'Test di attivazione')
        self.client=Client(self.web);self.client.ok('/api/auth')
    def tearDown(self):core.DB=self.old_db;core.revoke=self.old_revoke;self.tmp.cleanup()
    def enroll(self,client=None,username='admin',activation=None):
        client=client or self.client;client.ok('/api/auth');client.ok('/api/login',{'username':username,'password':PASSWORD})
        qr=client.ok('/api/enroll/start',{'activation':activation or self.activation});secret=qr['secret']
        result=client.ok('/api/enroll/confirm',{'code':pyotp.TOTP(secret).at(self.clock),'new_password':PERSONAL})
        return secret,result['recovery_codes']
    def new_user(self,role='operator',centers=None):
        username=role;result=self.client.ok('/api/user_save',{'user':{'username':username,'name':role,'role':role,'centers':centers if centers is not None else [self.cid],'active':True,'password':PASSWORD}})
        return result['activation_code']
    def login_factor(self,client,username='admin',code=None,recovery=False):
        client.ok('/api/auth');client.ok('/api/login',{'username':username,'password':PERSONAL})
        return client.call('/api/mfa',{'code':code,'recovery':recovery})
    def agreement_fixture(self):
        import agreements,rules
        snap=core.snapshot(self.admin,self.cid,'2026-02');core.mutate(self.admin,'person',{'cid':self.cid,'month':'2026-02','revision':snap['center']['revision'],'person':{'name':'Persona demo','role':'INF','note':'Nota economica riservata'}})
        snap=core.snapshot(self.admin,self.cid,'2026-02');pid=snap['people'][0]['id']
        return pid,{**agreements.proposal(rules.defaults(),{}),'basis':'all','fixed_deduction':0,'confirmed':True}
    def test_agreement_operator_cannot_read_or_write_and_state_redacted(self):
        self.enroll();pid,a=self.agreement_fixture();activation=self.new_user();op=Client(self.web);self.enroll(op,'operator',activation)
        self.assertEqual(op.call('/api/agreements?cid='+self.cid+'&month=2026-02')[0],403)
        self.assertEqual(op.call('/api/agreement_save',{'cid':self.cid,'month':'2026-02','person_id':pid,'agreement':a,'reason':'Test permessi'})[0],403)
        snap=op.ok('/api/state?cid='+self.cid+'&month=2026-02');self.assertNotIn('agreements',snap['period']);self.assertNotIn('Nota economica riservata',json.dumps(snap));self.assertNotIn('pay_override',json.dumps(snap))
    def test_agreement_requires_recent_2fa_and_preserves_month_and_center_scope(self):
        secret,codes=self.enroll();pid,a=self.agreement_fixture();self.clock+=601
        body={'cid':self.cid,'month':'2026-02','revision':core.snapshot(self.admin,self.cid,'2026-02')['center']['revision'],'person_id':pid,'agreement':a,'reason':'Accordo verificato'}
        self.assertEqual(self.client.call('/api/agreement_save',body)[0],428)
        self.client.ok('/api/security/stepup',{'password':PERSONAL,'code':pyotp.TOTP(secret).at(self.clock)})
        self.client.ok('/api/agreement_save',body);feb=self.client.ok('/api/agreements?cid='+self.cid+'&month=2026-02');mar=self.client.ok('/api/agreements?cid='+self.cid+'&month=2026-03')
        self.assertTrue(feb['rows'][0]['agreement']['confirmed']);self.assertFalse(mar['rows'][0]['agreement']['confirmed']);self.assertEqual(feb['rows'][0]['agreement']['version'],1)
        other=core.mutate(self.admin,'center_create',{'name':'Centro B','code':'BB'})['cid'];activation=self.new_user('manager');manager=Client(self.web);self.enroll(manager,'manager',activation)
        self.assertEqual(manager.call('/api/agreements?cid='+other+'&month=2026-02')[0],403)
        self.assertEqual(manager.call('/api/agreement_save',{**body,'cid':other})[0],403)
        body['revision']=core.snapshot(self.admin,self.cid,'2026-02')['center']['revision'];body['person_id']='foreign-person';self.assertEqual(manager.call('/api/agreement_save',body)[0],400)
    def test_closed_month_rejects_agreement_changes_and_stale_revision(self):
        self.enroll();pid,a=self.agreement_fixture();snap=core.snapshot(self.admin,self.cid,'2026-02');body={'cid':self.cid,'month':'2026-02','revision':snap['center']['revision'],'person_id':pid,'agreement':a,'reason':'Verifica accordo'}
        self.client.ok('/api/agreement_save',body);self.assertEqual(self.client.call('/api/agreement_save',body)[0],400)
        with core.connect() as c:
            ct=core.center(c,self.cid);p=core.period(c,ct,'2026-02');p['closed']=True;core.put_period(c,self.cid,'2026-02',p);c.commit()
        body['revision']=core.snapshot(self.admin,self.cid,'2026-02')['center']['revision'];self.assertEqual(self.client.call('/api/agreement_save',body)[0],400)
    def test_password_alone_never_authorizes_data(self):
        self.assertEqual(self.client.ok('/api/login',{'username':'admin','password':PASSWORD})['stage'],'enroll')
        for route in ['/api/state?cid='+self.cid+'&month=2026-10','/api/overview?month=2026-10','/api/export?cid='+self.cid+'&month=2026-10','/api/hr?cid='+self.cid,'/api/security','/api/statistics?from=2026-10&to=2026-10','/api/export_xlsx?kind=presenze_totali&from=2026-10&to=2026-10','/api/backups','/api/backup_download?filename=unknown']:
            with self.subTest(route=route):self.assertEqual(self.client.call(route)[0],403)
        self.assertEqual(self.client.call('/api/center_create',{'name':'Attacco','code':'X'})[0],403)
        self.assertEqual(self.client.call('/api/setup',{'username':'evil'})[0],403)
    def test_excel_download_and_private_export_need_recent_2fa(self):
        secret,codes=self.enroll();self.agreement_fixture()
        query='?from=2026-02&to=2026-02&cid='+self.cid+'&kind='
        result=self.client.ok('/api/export_xlsx'+query+'presenze_centro')
        self.assertTrue(result.startswith(b'PK'))
        self.assertEqual(self.client.headers['Content-Type'],'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment',self.client.headers['Content-Disposition'])
        self.clock+=601
        self.assertEqual(self.client.call('/api/export_xlsx'+query+'dipendenti')[0],428)
        self.assertEqual(self.client.call('/api/statistics?from=2026-02&to=2026-02')[0],200)
        self.client.ok('/api/security/stepup',{'password':PERSONAL,'code':pyotp.TOTP(secret).at(self.clock)})
        self.assertTrue(self.client.ok('/api/export_xlsx'+query+'dipendenti').startswith(b'PK'))
        activation=self.new_user();op=Client(self.web);self.enroll(op,'operator',activation)
        for route in ['/api/export_xlsx'+query+'dipendenti','/api/export_xlsx'+query+'accordi','/api/backups','/api/backup_download?filename=unknown']:
            self.assertEqual(op.call(route)[0],403)
    def test_backup_download_requires_recent_2fa_and_excludes_key(self):
        secret,codes=self.enroll();name=self.client.ok('/api/backup',{})['filename']
        listing=self.client.ok('/api/backups');self.assertIn(name,[x['filename'] for x in listing['files']])
        self.clock+=601
        path='/api/backup_download?filename='+name
        self.assertEqual(self.client.call(path)[0],428)
        self.client.ok('/api/security/stepup',{'password':PERSONAL,'code':pyotp.TOTP(secret).at(self.clock)})
        raw=self.client.ok(path);self.assertTrue(raw.startswith(b'SQLite format 3'))
        self.assertNotIn(self.key.read_bytes(),raw)
        self.assertEqual(self.client.headers['Content-Type'],'application/vnd.sqlite3')
    def test_activation_and_confirmation_are_required(self):
        self.client.ok('/api/login',{'username':'admin','password':PASSWORD})
        self.assertEqual(self.client.call('/api/enroll/start',{'activation':'inventato'})[0],400)
        self.assertEqual(self.client.call('/api/enroll/confirm',{'code':'123456','new_password':PERSONAL})[0],401)
        secret,codes=self.enroll();self.assertEqual(len(codes),10)
        self.assertEqual(self.client.ok('/api/auth')['stage'],'full')
        self.assertEqual(self.client.call('/api/enroll/start',{'activation':self.activation})[0],403)
        self.client.ok('/api/logout',{});self.assertEqual(self.client.call('/api/login',{'username':'admin','password':PASSWORD})[0],401)
    def test_qr_contains_local_enrollment_and_no_remote_service(self):
        self.client.ok('/api/login',{'username':'admin','password':PASSWORD})
        result=self.client.ok('/api/enroll/start',{'activation':self.activation})
        self.assertTrue(result['qr'].startswith('data:image/svg+xml;base64,'));self.assertEqual(len(result['secret']),32)
        self.assertNotIn('https://',base64.b64decode(result['qr'].split(',')[1]).decode())
    def test_cookie_csrf_rotation_and_csp(self):
        old_cookie=self.client.cookie;old_csrf=self.client.csrf
        self.client.ok('/api/login',{'username':'admin','password':PASSWORD})
        self.assertNotEqual(old_cookie,self.client.cookie);self.assertNotEqual(old_csrf,self.client.csrf)
        cookie=self.client.headers['Set-Cookie']
        for flag in ['__Host-presenze=','HttpOnly','SameSite=Strict','Secure','Path=/']:self.assertIn(flag,cookie)
        self.assertEqual(self.client.call('/api/logout',{},HTTP_X_PRESENZE_TOKEN=old_csrf)[0],403)
        self.client.ok('/');self.assertIn("script-src 'self';",self.client.headers['Content-Security-Policy'])
        self.assertEqual(self.client.headers['Cache-Control'],'no-store')
    def test_origin_host_csrf_and_unknown_routes(self):
        for header in [{'HTTP_HOST':'evil.test'},{'HTTP_ORIGIN':'https://evil.test'},{'HTTP_SEC_FETCH_SITE':'cross-site'}]:
            self.assertEqual(self.client.call('/api/auth',**header)[0],403)
        self.assertEqual(self.client.call('/api/login',{},HTTP_ORIGIN=None)[0],403)
        other=Client(self.web);other.ok('/api/auth')
        self.assertEqual(self.client.call('/api/login',{},HTTP_X_PRESENZE_TOKEN=other.csrf)[0],403)
        self.enroll();self.assertEqual(self.client.call('/api/setup',{})[0],404)
        for action in ('shutdown','sync_config','sync_now','local_setup'):self.assertEqual(self.client.call('/api/'+action,{})[0],404)
    def test_wrong_factor_replay_and_expiry(self):
        secret,codes=self.enroll();self.client.ok('/api/logout',{});self.client.ok('/api/login',{'username':'admin','password':PERSONAL})
        used=pyotp.TOTP(secret).at(self.clock);self.assertEqual(self.client.call('/api/mfa',{'code':used})[0],400)
        self.clock+=30;fresh=pyotp.TOTP(secret).at(self.clock);self.client.ok('/api/mfa',{'code':fresh})
        self.clock+=901;self.assertEqual(self.client.call('/api/state?cid='+self.cid+'&month=2026-10')[0],401)
        self.client.ok('/api/auth');self.client.ok('/api/login',{'username':'admin','password':PERSONAL});self.clock+=301
        self.assertEqual(self.client.call('/api/mfa',{'code':pyotp.TOTP(secret).at(self.clock)})[0],401)
    def test_recovery_is_one_use_and_still_requires_password(self):
        _,codes=self.enroll();self.client.ok('/api/logout',{})
        self.assertEqual(self.client.call('/api/mfa',{'code':codes[0],'recovery':True})[0],403)
        self.assertEqual(self.login_factor(self.client,code=codes[0],recovery=True)[0],200)
        self.assertEqual(self.client.ok('/api/security')['recovery_remaining'],9)
        self.client.ok('/api/logout',{});self.assertEqual(self.login_factor(self.client,code=codes[0],recovery=True)[0],400)
    def test_rate_limit_survives_new_challenge_and_process_object(self):
        _,codes=self.enroll();self.client.ok('/api/logout',{});self.client.ok('/api/login',{'username':'admin','password':PERSONAL})
        for _ in range(5):self.assertEqual(self.client.call('/api/mfa',{'code':'not-a-code'})[0],400)
        self.web.auth=Auth(self.key,clock=lambda:self.clock)
        self.client.ok('/api/logout',{});self.client.ok('/api/login',{'username':'admin','password':PERSONAL})
        self.assertEqual(self.client.call('/api/mfa',{'code':codes[0],'recovery':True})[0],429)
        self.clock+=301;self.client.ok('/api/auth');self.client.ok('/api/login',{'username':'admin','password':PERSONAL})
        self.assertEqual(self.client.call('/api/mfa',{'code':codes[0],'recovery':True})[0],200)
    def test_password_rate_limit(self):
        for _ in range(5):self.assertEqual(self.client.call('/api/login',{'username':'admin','password':'wrong'})[0],401)
        self.assertEqual(self.client.call('/api/login',{'username':'admin','password':PASSWORD})[0],429)
    def test_encrypted_secrets_and_hashed_recovery(self):
        secret,codes=self.enroll()
        with core.connect() as c:
            row=c.execute('SELECT * FROM web_security WHERE user_id=?',(self.uid,)).fetchone()
            self.assertNotIn(secret,json.dumps(dict(row)));self.assertEqual(self.web.auth.cipher.decrypt(row['secret'].encode()).decode(),secret)
            for code in codes:self.assertNotIn(code.replace('-',''),row['recovery'])
            events=''.join(str(tuple(x)) for x in c.execute('SELECT * FROM web_events'))
            self.assertNotIn(secret,events);self.assertNotIn(PERSONAL,events)
            self.assertTrue(all(not x[0].startswith('ey') for x in c.execute('SELECT id FROM web_sessions')))
        wrong=self.root/'wrong.key';Auth.create_key(wrong)
        with self.assertRaises(ValueError):Auth(wrong)
    def test_operator_scope_and_all_hr_routes(self):
        self.enroll();other=core.mutate(self.admin,'center_create',{'name':'Centro B','code':'CENTRO-B'})['cid'];activation=self.new_user()
        operator=Client(self.web);self.enroll(operator,'operator',activation)
        self.assertEqual([x['id'] for x in operator.ok('/api/overview?month=2026-10')['centers']],[self.cid])
        for route in ['/api/state?cid='+other+'&month=2026-10','/api/hr?cid='+self.cid,'/api/hr_document?cid='+self.cid+'&id=x']:
            self.assertEqual(operator.call(route)[0],403)
        for action in ('user_save','center_create','hr_save','hr_task','hr_document_add','hr_document_delete','hr_settings'):
            self.assertEqual(operator.call('/api/'+action,{'cid':self.cid,'user':{}})[0],403)
    def test_manager_own_hr_and_config_without_global_privilege(self):
        self.enroll();other=core.mutate(self.admin,'center_create',{'name':'Centro B','code':'CENTRO-B'})['cid'];activation=self.new_user('manager')
        manager=Client(self.web);self.enroll(manager,'manager',activation)
        manager.ok('/api/hr?cid='+self.cid)
        for action in ('hr_save','hr_settings','center_save','person'):
            self.assertEqual(manager.call('/api/'+action,{'cid':other})[0],403)
        for action in ('user_save','center_create','backup','security/reset_user'):
            self.assertEqual(manager.call('/api/'+action,{'cid':self.cid})[0],403)
        s=manager.ok('/api/state?cid='+self.cid+'&month=2026-10')
        manager.ok('/api/center_save',{'cid':self.cid,'revision':s['center']['revision'],'config':s['center']['config']})
    def test_viewer_read_only_and_group_export_scope(self):
        self.enroll();activation=self.new_user('viewer');reader=Client(self.web);self.enroll(reader,'viewer',activation)
        self.assertEqual(reader.call('/api/group_export?month=2026-10')[0],200)
        s=reader.ok('/api/state?cid='+self.cid+'&month=2026-10')
        self.assertEqual(reader.call('/api/entry',{'cid':self.cid,'month':'2026-10','revision':s['center']['revision']})[0],403)
    def test_stepup_required_and_cannot_be_spoofed(self):
        secret,_=self.enroll();self.clock+=301
        self.assertEqual(self.client.call('/api/security/recovery',{'verified':self.clock})[0],428)
        self.assertEqual(self.client.call('/api/security/stepup',{'password':'wrong','code':pyotp.TOTP(secret).at(self.clock)})[0],400)
        self.client.ok('/api/security/stepup',{'password':PERSONAL,'code':pyotp.TOTP(secret).at(self.clock)})
        self.assertEqual(len(self.client.ok('/api/security/recovery',{})['recovery_codes']),10)
    def test_rotation_revokes_old_factor_codes_and_other_sessions(self):
        secret,codes=self.enroll();second=Client(self.web);self.assertEqual(self.login_factor(second,code=codes[0],recovery=True)[0],200)
        new=self.client.ok('/api/security/rotate/start',{})['secret'];self.assertNotEqual(secret,new)
        out=self.client.ok('/api/security/rotate/confirm',{'code':pyotp.TOTP(new).at(self.clock)})
        self.assertEqual(second.call('/api/security')[0],401)
        self.client.ok('/api/logout',{});self.client.ok('/api/login',{'username':'admin','password':PERSONAL});self.clock+=30
        self.assertEqual(self.client.call('/api/mfa',{'code':pyotp.TOTP(secret).at(self.clock)})[0],400)
        self.assertEqual(self.client.call('/api/mfa',{'code':codes[1],'recovery':True})[0],400)
        self.assertEqual(self.client.call('/api/mfa',{'code':out['recovery_codes'][0],'recovery':True})[0],200)
    def test_admin_reset_requires_reason_and_invalidates_enrollment(self):
        self.enroll();activation=self.new_user();operator=Client(self.web);self.enroll(operator,'operator',activation)
        with core.connect() as c:uid=c.execute("SELECT id FROM users WHERE username='operator'").fetchone()[0]
        self.assertEqual(self.client.call('/api/security/reset_user',{'user_id':uid,'reason':''})[0],400)
        new=self.client.ok('/api/security/reset_user',{'user_id':uid,'reason':'Identità verificata dal referente'})['activation_code']
        self.assertEqual(operator.call('/api/security')[0],401)
        operator.ok('/api/auth');operator.ok('/api/login',{'username':'operator','password':PERSONAL})
        self.assertEqual(operator.call('/api/enroll/start',{'activation':activation})[0],400)
        operator.ok('/api/enroll/start',{'activation':new})
    def test_password_change_keeps_2fa_and_revokes_sessions(self):
        _,codes=self.enroll();self.client.ok('/api/password',{'current':PERSONAL,'password':'Password-aggiornata-2026!'})
        self.assertEqual(self.client.call('/api/security')[0],401);self.client.ok('/api/auth')
        self.assertEqual(self.client.ok('/api/login',{'username':'admin','password':'Password-aggiornata-2026!'})['stage'],'mfa')
        self.client.ok('/api/mfa',{'code':codes[0],'recovery':True})
    def test_concurrent_recovery_code_consumption_accepts_only_one(self):
        _,codes=self.enroll();clients=[Client(self.web),Client(self.web)]
        for c in clients:c.ok('/api/auth');c.ok('/api/login',{'username':'admin','password':PERSONAL})
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda c:c.call('/api/mfa',{'code':codes[0],'recovery':True})[0],clients))
        self.assertEqual(sorted(results),[200,400])
    def test_backup_contains_encrypted_mfa_and_hr_schema(self):
        self.enroll();name=self.client.ok('/api/backup',{})['filename']
        with sqlite3.connect(core.DB.parent/'backups'/name) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('SELECT enabled FROM web_security').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM hr_documents').fetchone()[0],0)
    def test_no_public_http_configuration(self):
        for origin in ('http://presenze.test','http://192.0.2.1:8080'):
            with self.assertRaises(ValueError):WebApp(self.root/'data',self.key,origin,dev=True)

    def test_restore_database_and_key_preserves_hr_document_and_2fa(self):
        _,codes=self.enroll();snap=self.client.ok('/api/state?cid='+self.cid+'&month=2026-10')
        pid=self.client.ok('/api/hr_save',dict(cid=self.cid,revision=snap['center']['revision'],version=0,name='Persona ripristino demo',registration='RESTORE001',role='INF',active=True,stage='incoming',fields={'identity_number':'DOC-RESTORE-DEMO','bank_name':'Banca demo'},custom={}))['pid']
        payload=base64.b64encode(b'%PDF-1.4\nRestore fixture\n%%EOF').decode()
        doc=self.client.ok('/api/hr_document_add',dict(cid=self.cid,pid=pid,name='ripristino-demo.pdf',category='Contratto',expiry='',content=payload))['id']
        source=core.DB.parent/'backups'/self.client.ok('/api/backup',{})['filename']
        restored=self.root/'restored';restored.mkdir();shutil.copyfile(source,restored/'presenze.sqlite3')
        wrong=self.root/'wrong.key';Auth.create_key(wrong)
        with self.assertRaisesRegex(ValueError,'non corrispondente'):WebApp(restored,wrong,'https://restored.test')
        application=WebApp(restored,self.key,'https://restored.test');application.auth.clock=lambda:self.clock
        client=Client(application);status,_=self.login_factor(client,code=codes[0],recovery=True);self.assertEqual(status,200)
        record=client.ok('/api/hr?cid='+self.cid+'&pid='+pid)
        self.assertEqual(record['profile']['fields']['identity_number'],'DOC-RESTORE-DEMO')
        self.assertEqual(client.ok('/api/hr_document?cid='+self.cid+'&id='+doc)['content'],payload)
        with core.connect() as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(list(c.execute('PRAGMA foreign_key_check')),[])
    def test_after_restore_revokes_sessions_recovery_and_activation_preserving_totp(self):
        import manage
        secret,codes=self.enroll();self.new_user()
        with patch('sys.argv',['manage.py','after-restore','--data-dir',str(core.DB.parent),'--key-file',str(self.key)]),patch('builtins.input',return_value='CONFERMO'),redirect_stdout(io.StringIO()):
            manage.main()
        with core.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM web_sessions').fetchone()[0],0)
            for row in c.execute('SELECT recovery,activation,activation_until FROM web_security'):
                self.assertEqual(tuple(row),('[]','',0))
            self.assertEqual(c.execute('SELECT enabled FROM web_security WHERE user_id=?',(self.uid,)).fetchone()[0],1)
        self.assertEqual(self.client.call('/api/security')[0],401)
        self.assertEqual(self.login_factor(self.client,code=codes[0],recovery=True)[0],400)
        self.clock+=30
        self.client.ok('/api/mfa',{'code':pyotp.TOTP(secret).at(self.clock)})
        self.assertEqual(len(self.client.ok('/api/security/recovery',{})['recovery_codes']),10)
    def test_rfc6238_reference_vectors(self):
        secret=base64.b32encode(b'12345678901234567890').decode();t=pyotp.TOTP(secret,digits=8)
        for stamp,expected in [(59,'94287082'),(1111111109,'07081804'),(1111111111,'14050471'),(1234567890,'89005924'),(2000000000,'69279037'),(20000000000,'65353130')]:
            self.assertEqual(t.at(stamp),expected)

if __name__=='__main__':unittest.main(verbosity=2)
