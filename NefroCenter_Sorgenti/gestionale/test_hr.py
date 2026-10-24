import base64,copy,json,sqlite3,tempfile,unittest,concurrent.futures
from pathlib import Path
import core as app
import hr

class HRTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.previous=app.DB;app.DB=Path(self.tmp.name)/'private'/'presenze.sqlite3';app.init_db();app.SESSIONS.clear();app.FAILURES.clear()
        app.setup(dict(username='admin',name='Admin',center_name='Centro demo',password='Password-test-2026!'))
        _,self.user=app.login(dict(username='admin',password='Password-test-2026!'))
        with app.connect() as c:self.cid=app.centers_for(c,self.user)[0]['id']
    def tearDown(self):app.DB=self.previous;self.tmp.cleanup()
    def req(self,**extra):
        with app.connect() as c:revision=app.center(c,self.cid)['revision']
        return dict(cid=self.cid,revision=revision,version=0,name='Persona dimostrativa',role='INF',registration='D001',active=True,stage='incoming',fields={'start_date':'2026-10-20','iban':'IT60X0542811101000000123456','notes':'RISERVATO-HR'},custom={},**extra)
    def create(self):return hr.save(app,self.user,self.req())['pid']
    def test_create_links_attendance_without_disclosing_hr(self):
        pid=self.create();s=app.snapshot(self.user,self.cid,'2026-10');self.assertEqual(s['people'][0]['id'],pid);self.assertNotIn('RISERVATO-HR',json.dumps(s));d=hr.read(app,self.user,self.cid,pid);self.assertEqual(d['profile']['fields']['iban'],'IT60X0542811101000000123456');self.assertEqual(d['progress']['total'],14);self.assertEqual(d['profile']['tasks'][0]['due'],'2026-10-13')
    def test_operator_and_viewer_denied_all_hr_access(self):
        pid=self.create()
        for role in ('operator','viewer'):
            app.mutate(self.user,'user_save',{'user':dict(username=role,name=role,role=role,centers=[self.cid],active=True,password='Password-test-2026!')})
            _,u=app.login(dict(username=role,password='Password-test-2026!'))
            calls=[lambda:hr.read(app,u,self.cid),lambda:hr.read(app,u,self.cid,pid),lambda:hr.save(app,u,self.req()),lambda:hr.task_save(app,u,{'cid':self.cid,'pid':pid}),lambda:hr.document_read(app,u,self.cid,'not-existing'),lambda:hr.document_add(app,u,{'cid':self.cid,'pid':pid}),lambda:hr.document_delete(app,u,{'cid':self.cid,'id':'x','reason':'r'}),lambda:hr.settings_save(app,u,{'cid':self.cid,'settings':hr.read(app,self.user,self.cid)['settings']})]
            for call in calls:
                with self.subTest(role=role),self.assertRaises(PermissionError):call()
    def test_revocation_is_checked_again(self):
        pid=self.create();stale=dict(self.user)
        with app.connect() as c:c.execute('UPDATE users SET role=? WHERE id=?',('viewer',self.user['id']));c.commit()
        with self.assertRaises(PermissionError):hr.read(app,stale,self.cid,pid)
    def test_version_conflicts_do_not_overwrite(self):
        pid=self.create();r=self.req();r.update(pid=pid,version=1);hr.save(app,self.user,r)
        r['revision']=self.req()['revision']
        with self.assertRaisesRegex(ValueError,'altra sessione'):hr.save(app,self.user,r)
        d=hr.read(app,self.user,self.cid,pid);self.assertEqual(d['profile']['version'],2);self.assertEqual(len(d['history']),2)
    def test_iban_dates_and_duplicate_matricola(self):
        for fields in ({'iban':'IT60X0542811101000000123457'},{'birth_date':'2030-01-01'},{'start_date':'2026-10-20','end_date':'2026-10-01'},{'weekly_hours':'nan'}):
            r=self.req();r['fields']=fields
            with self.subTest(fields=fields),self.assertRaises(ValueError):hr.save(app,self.user,r)
        self.create()
        with self.assertRaisesRegex(ValueError,'Matricola'):hr.save(app,self.user,self.req())
    def test_tasks_na_reason_and_audit(self):
        pid=self.create();r=dict(cid=self.cid,pid=pid,version=1,task_id='permesso',status='na',note='',due='',owner='HR')
        with self.assertRaises(ValueError):hr.task_save(app,self.user,r)
        r['note']='Non pertinente al rapporto';hr.task_save(app,self.user,r);d=hr.read(app,self.user,self.cid,pid);t=next(t for t in d['profile']['tasks'] if t['id']=='permesso');self.assertEqual(t['completed_by'],'admin');self.assertTrue(t['completed_at']);self.assertEqual(d['progress']['done'],1)
        with self.assertRaises(ValueError):hr.task_save(app,self.user,r)
    def test_template_preserves_existing_checklist_and_supports_custom_fields(self):
        pid=self.create();cfg=hr.read(app,self.user,self.cid)['settings'];cfg['tasks']=cfg['tasks'][:2];cfg['fields']=[dict(id='badge',label='Numero badge',type='text',required=True)];hr.settings_save(app,self.user,{'cid':self.cid,'settings':cfg});d=hr.read(app,self.user,self.cid,pid);self.assertEqual(len(d['profile']['tasks']),14)
        r=self.req();r.update(name='Seconda persona',registration='D002',custom={'badge':'A123'});second=hr.save(app,self.user,r)['pid'];d=hr.read(app,self.user,self.cid,second);self.assertEqual(len(d['profile']['tasks']),2);self.assertEqual(d['profile']['custom']['badge'],'A123')
    def test_document_integrity_access_and_backup(self):
        pid=self.create();data=b'%PDF-1.4\nTest fixture\n%%EOF';r=dict(cid=self.cid,pid=pid,name='contratto.pdf',category='Contratto',expiry='2026-12-31',content=base64.b64encode(data).decode());doc=hr.document_add(app,self.user,r)
        self.assertEqual(base64.b64decode(hr.document_read(app,self.user,self.cid,doc['id'])['content']),data)
        backup=app.backup(self.user);c=sqlite3.connect(app.DB.parent/'backups'/backup['filename']);self.assertEqual(c.execute('SELECT content FROM hr_documents').fetchone()[0],data);c.close()
        for name,content in [('../contratto.pdf',data),('file.html',b'<html>'),('falso.pdf',b'<html>')]:
            with self.subTest(name=name),self.assertRaises(ValueError):hr.document_add(app,self.user,{**r,'name':name,'content':base64.b64encode(content).decode()})
        other=app.mutate(self.user,'center_create',{'name':'Altro centro','code':'ALTRO'})['cid']
        with self.assertRaises(ValueError):hr.document_read(app,self.user,other,doc['id'])
        with self.assertRaises(ValueError):hr.document_delete(app,self.user,{'cid':self.cid,'id':doc['id'],'reason':''})
    def test_complete_fields_saved_and_kept_out_of_attendance(self):
        r=self.req();r['fields'].update(identity_type='Documento demo',identity_number='DOC-DEMO',identity_issued_date='2025-01-01',identity_expiry='2027-01-01',pec='persona@example.invalid',company_email='ufficio@example.invalid',bank_name='Banca demo',account_holder='Persona dimostrativa',payment_method='Bonifico',contract_type='Contratto demo',badge_number='BADGE-DEMO',cost_center='AREA-01',workplace='Centro demo',tutor='Tutor demo',vat_number='DEMO-PIVA')
        pid=hr.save(app,self.user,r)['pid'];d=hr.read(app,self.user,self.cid,pid)
        for k,v in r['fields'].items():self.assertEqual(d['profile']['fields'][k],v)
        snapshot=app.snapshot(self.user,self.cid,'2026-10');self.assertEqual(snapshot['people'][0]['contract'],'Contratto demo')
        for private in ['DOC-DEMO','ufficio@example.invalid','Banca demo','BADGE-DEMO','DEMO-PIVA']:self.assertNotIn(private,json.dumps(snapshot))
    def test_identity_dates_and_new_emails_validated(self):
        for fields in ({'identity_issued_date':'2027-01-01','identity_expiry':'2026-01-01'},{'pec':'non valida'},{'company_email':'not-an-email'}):
            r=self.req();r['fields']=fields
            with self.subTest(fields=fields),self.assertRaises(ValueError):hr.save(app,self.user,r)
    def test_new_fields_merge_legacy_profile_without_data_loss(self):
        pid=self.create()
        with app.connect() as c:
            data=json.loads(c.execute('SELECT data FROM hr_profiles WHERE cid=? AND pid=?',(self.cid,pid)).fetchone()[0]);data['fields'].pop('identity_number',None);data['fields'].pop('bank_name',None);c.execute('UPDATE hr_profiles SET data=? WHERE cid=? AND pid=?',(app.dump(data),self.cid,pid));c.commit()
        old=hr.read(app,self.user,self.cid,pid);self.assertEqual(old['profile']['fields']['bank_name'],'');self.assertEqual(old['profile']['fields']['notes'],'RISERVATO-HR')
        r=self.req();r.update(pid=pid,version=1,fields=old['profile']['fields']);r['fields']['bank_name']='Banca demo';hr.save(app,self.user,r);self.assertEqual(hr.read(app,self.user,self.cid,pid)['profile']['fields']['iban'],'IT60X0542811101000000123456')
    def test_personal_deadlines_include_identity_and_document(self):
        r=self.req();r['fields']['identity_expiry']='2026-01-01';pid=hr.save(app,self.user,r)['pid'];hr.document_add(app,self.user,dict(cid=self.cid,pid=pid,name='attestato.pdf',category='Formazione',expiry='2030-01-01',content=base64.b64encode(b'%PDF-1.4\nDemo').decode()))
        d=hr.read(app,self.user,self.cid,pid);self.assertTrue(any(x['label']=='Documento di identità' and x['section']=='anagrafica' and x['late'] for x in d['deadlines']));self.assertTrue(any(x['date']=='2030-01-01' and x['section']=='documenti' for x in d['deadlines']))
        self.assertTrue(any(x['label']=='Documento di identità' for x in hr.read(app,self.user,self.cid)['deadlines']))

    def test_concurrent_profile_edits_keep_one_consistent_version(self):
        pid=self.create();base=self.req();base.update(pid=pid,version=1)
        def write(label):
            body=copy.deepcopy(base);body['fields']['bank_name']=label
            try:return ('saved',label,hr.save(app,self.user,body))
            except ValueError:return ('conflict',label,None)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(write,['Banca A demo','Banca B demo']))
        self.assertEqual(sorted(r[0] for r in results),['conflict','saved'])
        winner=next(r[1] for r in results if r[0]=='saved')
        record=hr.read(app,self.user,self.cid,pid)
        self.assertEqual(record['profile']['fields']['bank_name'],winner)
        self.assertEqual(record['profile']['version'],2)
        self.assertEqual(len(record['history']),2)

if __name__=='__main__':unittest.main()
