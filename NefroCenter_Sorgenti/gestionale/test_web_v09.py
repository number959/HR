"""New HTTP boundaries, binary previews, guide streaming and additive upgrade."""
import base64
import sqlite3
import unittest
import core
import hr
import test_web as fixturemodule
Client=fixturemodule.Client


class WebV09Tests(unittest.TestCase):
    setUp=fixturemodule.WebTests.setUp
    tearDown=fixturemodule.WebTests.tearDown
    enroll=fixturemodule.WebTests.enroll
    new_user=fixturemodule.WebTests.new_user

    def test_hr_end_to_end_document_preview_and_admin_separation(self):
        self.enroll()
        other=core.mutate(self.admin,'center_create',dict(name='Centro remoto',code='REM'))['cid']
        pid=hr.save(core,self.admin,dict(cid=other,revision=0,version=0,name='Persona remota',role='INF',active=True,stage='active',fields={},custom={}))['pid']
        content=b'%PDF-1.4\nRemote document fixture\n%%EOF'
        doc=hr.document_add(core,self.admin,dict(cid=other,pid=pid,name='remoto.pdf',content=base64.b64encode(content).decode()))['id']
        activation=self.client.ok('/api/user_save',{'user':{'username':'hrcentrale','name':'HR centrale','role':'hr','centers':[],'active':True,'password':fixturemodule.PASSWORD}})['activation_code']
        client=Client(self.web);self.enroll(client,'hrcentrale',activation)
        index=client.ok('/api/hr_documents');self.assertEqual(index['documents'][0]['id'],doc)
        self.assertEqual(client.ok('/api/hr_document_view?cid='+other+'&id='+doc),content)
        self.assertEqual(client.headers['Content-Type'],'application/pdf')
        self.assertEqual(client.headers['Cache-Control'],'no-store')
        self.assertEqual(client.headers['Content-Disposition'],'inline')
        self.assertIn('sandbox',client.headers['Content-Security-Policy'])
        for path in ('/api/backups','/api/backup_policy'):
            self.assertEqual(client.call(path)[0],403)
        self.assertEqual(client.call('/api/center_save',dict(cid=other))[0],403)
        self.assertEqual(client.ok('/api/state?cid='+other+'&month=2026-10')['users'],[])
        activation=self.new_user('operator');op=Client(self.web);self.enroll(op,'operator',activation)
        for path in ('/api/hr_documents','/api/hr_document_view?cid='+other+'&id='+doc,'/api/workforce','/api/payroll_config?cid='+other):
            self.assertEqual(op.call(path)[0],403)
        public=Client(self.web)
        self.assertNotEqual(public.call('/api/hr_document_view?cid='+other+'&id='+doc)[0],200)

    def test_new_routes_and_stepup_preserve_disabled_nas_and_draft_payroll(self):
        self.enroll()
        self.assertFalse(self.client.ok('/api/backup_policy')['enabled'])
        self.assertEqual(self.client.ok('/api/workforce')['groups'],[])
        self.assertIsInstance(self.client.ok('/api/tasks?month=2026-10')['items'],list)
        self.assertEqual(self.client.ok('/api/payroll_config?cid='+self.cid)['config']['status'],'draft')
        self.assertFalse(self.client.ok('/api/payroll_preview?cid='+self.cid+'&from=2026-10&to=2026-10')['can_download'])
        self.clock+=601
        for action in ('backup_policy_save','backup_policy_run','workforce_contract','workforce_link','workforce_apply','payroll_save'):
            self.assertEqual(self.client.call('/api/'+action,dict(cid=self.cid))[0],428)

    def test_guide_assets_range_and_path_allowlist(self):
        path='/assets/guides/presenze.mp4'
        status,full=self.client.call(path);self.assertEqual(status,200)
        status,part=self.client.call(path,HTTP_RANGE='bytes=10-29')
        self.assertEqual((status,part),(206,full[10:30]))
        self.assertEqual(self.client.headers['Content-Range'],f'bytes 10-29/{len(full)}')
        status,part=self.client.call(path,HTTP_RANGE='bytes=-15');self.assertEqual((status,part),(206,full[-15:]))
        self.assertEqual(self.client.call(path,HTTP_RANGE='bytes=999999999-')[0],416)
        self.assertIn(b'WEBVTT',self.client.ok('/assets/guides/presenze.vtt'))
        for target in ('/assets/../core.py','/assets/guides/../../core.py','/assets/guides/manifest.json'):
            self.assertNotEqual(self.client.call(target)[0],200)

    def test_illustrated_help_public_assets_and_boundary(self):
        # These files contain only the synthetic demonstration material.
        for path, mime, signature in (
            ('/assets/guida_illustrata.pdf', 'application/pdf', b'%PDF-'),
            ('/assets/guide_screens/presenze.webp', 'image/webp', b'RIFF'),
            ('/assets/guides/presenze.jpg', 'image/jpeg', b'\xff\xd8\xff'),
        ):
            status, content = self.client.call(path)
            self.assertEqual(status, 200, path)
            self.assertEqual(self.client.headers['Content-Type'], mime, path)
            self.assertTrue(content.startswith(signature), path)
        for path in ('/assets/guide_screens/manifest.json',
                     '/assets/guide_screens/../../core.py',
                     '/assets/guide_screens/presenze.png',
                     '/assets/guides/../guide_screens/manifest.json'):
            self.assertNotEqual(self.client.call(path)[0], 200, path)

    def test_upgrade_snapshots_old_database_before_new_schema(self):
        with core.connect() as c:
            for table in ('workforce_history','workforce_contracts','workforce_economics','workforce_assignments','group_people','payroll_templates'):
                c.execute('DROP TABLE '+table)
            c.execute('PRAGMA user_version=5');c.commit()
        before=set((core.DB.parent/'backups').glob('*.sqlite3'));core.init_db()
        created=set((core.DB.parent/'backups').glob('*.sqlite3'))-before
        self.assertEqual(len(created),1)
        with sqlite3.connect(next(iter(created))) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],5)
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='group_people'").fetchone())
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],1)
        with core.connect() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],8)
            self.assertIsNotNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='group_people'").fetchone())
        core.init_db();self.assertEqual(set((core.DB.parent/'backups').glob('*.sqlite3'))-before,created)
