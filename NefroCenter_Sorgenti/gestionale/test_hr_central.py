"""HR centrale: documenti remoti, isolamento dei centri e separazione dall'amministratore."""
import base64
import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import core
import hr


class CentralHRTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.previous=core.DB
        core.DB=Path(self.tmp.name)/'private'/'presenze.sqlite3'
        core.init_db();core.SESSIONS.clear();core.FAILURES.clear()
        core.setup(dict(username='admin',name='Amministratore',center_name='Sede Uno',password='Password-test-2026!'))
        with core.connect() as c:
            self.admin=core.public_user(c.execute("SELECT * FROM users WHERE username='admin'").fetchone())
            self.one=core.centers_for(c,self.admin)[0]['id']
        self.two=core.mutate(self.admin,'center_create',{'name':'Sede Due','code':'DUE'})['cid']
        self.hr=self.user('ufficiohr','hr',[])
        self.manager=self.user('responsabile','manager',[self.one])

    def tearDown(self):
        core.DB=self.previous;self.tmp.cleanup()

    def user(self,username,role,centers):
        core.mutate(self.admin,'user_save',{'user':dict(username=username,name=username,role=role,centers=centers,active=True,password='Password-test-2026!')})
        with core.connect() as c:return core.public_user(c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone())

    def profile(self,cid,name='Persona demo',user=None):
        with core.connect() as c:revision=core.center(c,cid)['revision']
        return hr.save(core,user or self.admin,dict(cid=cid,revision=revision,version=0,name=name,role='INF',registration='MAT-'+name,active=True,stage='incoming',fields={},custom={}))['pid']

    def upload(self,cid,pid,user=None,name='contratto.pdf',expiry='',category='Contratto'):
        content=b'%PDF-1.4\nDocumento demo\n%%EOF'
        result=hr.document_add(core,user or self.admin,dict(cid=cid,pid=pid,name=name,category=category,expiry=expiry,content=base64.b64encode(content).decode()))
        return result['id'],content

    def test_hr_is_global_including_new_centers_without_being_admin(self):
        self.assertEqual(self.hr['centers'],[])
        third=core.mutate(self.admin,'center_create',{'name':'Sede Nuova','code':'NUOVA'})['cid']
        with core.connect() as c:self.assertEqual({self.one,self.two,third},{ct['id'] for ct in core.centers_for(c,self.hr)})
        self.assertEqual(core.snapshot(self.hr,third,'2026-10')['center']['id'],third)
        for call in (lambda:core.require_admin(self.hr),lambda:core.require_manager(self.hr,self.one),lambda:core.authorize(self.hr,self.one,write=True),lambda:core.backup(self.hr)):
            with self.assertRaises(PermissionError):call()

    def test_remote_manager_upload_is_immediately_visible_and_audited_for_central_hr(self):
        pid=self.profile(self.one,user=self.manager)
        docid,content=self.upload(self.one,pid,self.manager)
        index=hr.document_index(core,self.hr)
        self.assertEqual(index['total'],1)
        doc=index['documents'][0]
        self.assertEqual((doc['cid'],doc['pid'],doc['uploaded_by']),(self.one,pid,self.manager['username']))
        self.assertNotIn('content',doc)
        self.assertEqual(hr.document_view(core,self.hr,self.one,docid),(content,'application/pdf','contratto.pdf'))
        self.assertEqual(base64.b64decode(hr.document_read(core,self.hr,self.one,docid)['content']),content)
        with core.connect() as c:
            events=[dict(r) for r in c.execute('SELECT username,action,after_data FROM audit WHERE cid=? ORDER BY id',(self.one,))]
        viewed=next(e for e in events if e['action']=='Documento dipendente visualizzato')
        self.assertEqual(viewed['username'],'ufficiohr')
        self.assertEqual(json.loads(viewed['after_data'])['sha256'],hashlib.sha256(content).hexdigest())
        self.assertNotIn(content.decode(),json.dumps(events))

    def test_hr_can_manage_profiles_and_onboarding_in_other_center(self):
        pid=self.profile(self.two,'Nuovo ingresso',self.hr)
        record=hr.read(core,self.hr,self.two,pid)
        self.assertEqual(record['profile']['version'],1)
        task=record['profile']['tasks'][0]
        hr.task_save(core,self.hr,dict(cid=self.two,pid=pid,version=1,task_id=task['id'],status='done',note='',due='',owner='HR centrale'))
        self.assertEqual(hr.read(core,self.hr,self.two,pid)['progress']['done'],1)
        cfg=hr.read(core,self.hr,self.two)['settings']
        hr.settings_save(core,self.hr,{'cid':self.two,'settings':cfg})
        docid,_=self.upload(self.two,pid,self.hr)
        hr.document_delete(core,self.hr,{'cid':self.two,'id':docid,'reason':'Allegato dimostrativo sostituito'})
        self.assertEqual(hr.document_index(core,self.hr)['total'],0)

    def test_hr_cannot_write_attendance_parameters_users_or_close_month(self):
        with core.connect() as c:revision=core.center(c,self.one)['revision']
        for action in ('entry','delete','person','patient','center_save','period_verify','close','reopen','apply_rules','agreement_save','user_save','center_create'):
            with self.subTest(action=action),self.assertRaises(PermissionError):
                core.mutate(self.hr,action,{'cid':self.one,'month':'2026-10','revision':revision})

    def test_manager_listing_and_document_identifiers_cannot_cross_centers(self):
        p1=self.profile(self.one);p2=self.profile(self.two)
        d1,_=self.upload(self.one,p1);d2,_=self.upload(self.two,p2)
        self.assertEqual({d['id'] for d in hr.document_index(core,self.manager)['documents']},{d1})
        for call in (lambda:hr.document_index(core,self.manager,self.two),lambda:hr.document_view(core,self.manager,self.two,d2),lambda:hr.document_read(core,self.manager,self.two,d2),lambda:hr.read(core,self.manager,self.two,p2)):
            with self.assertRaises(PermissionError):call()
        with self.assertRaises(ValueError):hr.document_view(core,self.manager,self.one,d2)
        with self.assertRaises(ValueError):hr.document_view(core,self.hr,self.one,'../../etc/passwd')

    def test_operator_viewer_and_revoked_accounts_cannot_read_metadata_or_documents(self):
        pid=self.profile(self.one);docid,_=self.upload(self.one,pid)
        for role in ('operator','viewer'):
            user=self.user(role,role,[self.one])
            for call in (lambda:hr.document_index(core,user),lambda:hr.document_view(core,user,self.one,docid),lambda:hr.document_read(core,user,self.one,docid)):
                with self.subTest(role=role),self.assertRaises(PermissionError):call()
        stale=dict(self.hr)
        with core.connect() as c:c.execute("UPDATE users SET role='viewer',centers=? WHERE id=?",(core.dump([self.one]),self.hr['id']));c.commit()
        with self.assertRaises(PermissionError):hr.document_index(core,stale)
        with self.assertRaises(PermissionError):hr.document_view(core,stale,self.one,docid)

    def test_central_filters_dates_person_category_and_center(self):
        p1=self.profile(self.one,'Mario Rossi');p2=self.profile(self.two,'Lucia Verdi')
        yesterday=(date.today()-timedelta(days=1)).isoformat();tomorrow=(date.today()+timedelta(days=1)).isoformat()
        expired,_=self.upload(self.one,p1,expiry=yesterday,category='Identità')
        upcoming,_=self.upload(self.two,p2,expiry=tomorrow)
        undated,_=self.upload(self.one,p1,name='modulo.pdf',category='Modulo')
        def ids(**filters):return {d['id'] for d in hr.document_index(core,self.hr,**filters)['documents']}
        self.assertEqual(ids(expiry='expired'),{expired})
        self.assertEqual(ids(expiry='soon'),{upcoming})
        self.assertEqual(ids(expiry='none'),{undated})
        self.assertEqual(ids(expiry='dated'),{expired,upcoming})
        self.assertEqual(ids(person='mario',category='Modulo',cid=self.one),{undated})
        self.assertEqual(ids(person='MAT-Lucia'),{upcoming})
        with self.assertRaises(ValueError):hr.document_index(core,self.hr,expiry='invalid')

    def test_preview_mime_and_integrity_checks(self):
        pid=self.profile(self.one)
        for name,content,mime in [('immagine.png',b'\x89PNG\r\n\x1a\nDEMO','image/png'),('immagine.jpg',b'\xff\xd8\xffDEMO','image/jpeg')]:
            doc=hr.document_add(core,self.manager,dict(cid=self.one,pid=pid,name=name,category='Documento',content=base64.b64encode(content).decode()))
            self.assertEqual(hr.document_view(core,self.hr,self.one,doc['id']),(content,mime,name))
        docid,content=self.upload(self.one,pid)
        with core.connect() as c:c.execute('UPDATE hr_documents SET content=? WHERE id=?',(content+b'alterato',docid));c.commit()
        with self.assertRaisesRegex(ValueError,'non valido'):hr.document_view(core,self.hr,self.one,docid)
        with self.assertRaises(ValueError):self.upload(self.one,pid,name='nome\r\nInjection.pdf')


if __name__=='__main__':unittest.main()
