import base64,json,sqlite3,tempfile,unittest
from pathlib import Path
import core,hr
from migrate_desktop import import_backup

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.old=core.DB;self.old_revoke=core.revoke;core.revoke=lambda uid:None
        core.DB=self.root/'source'/'presenze.sqlite3';core.init_db();core.setup(dict(username='admin',password='Password-migration-2026!',name='Origine',center_name='Sede origine'))
        with core.connect() as c:self.user=core.public_user(c.execute('SELECT * FROM users').fetchone());self.cid=core.centers_for(c,self.user)[0]['id']
        self.pid=hr.save(core,self.user,dict(cid=self.cid,version=0,revision=0,name='Dipendente test',role='INF',registration='MIG001',active=True,stage='active',fields={'iban':'IT60X0542811101000000123456','start_date':'2026-10-01'},custom={}))['pid']
        hr.document_add(core,self.user,dict(cid=self.cid,pid=self.pid,name='documento.pdf',content=base64.b64encode(b'%PDF-1.4\nfixture\n%%EOF').decode()))
        core.mutate(self.user,'entry',dict(cid=self.cid,month='2026-10',revision=1,entry=dict(person_id=self.pid,day='2026-10-01',slot='m',code='m',layer='actual')))
        # Desktop fixture: the source predates group identities and payroll templates.
        with core.connect() as c:
            for table in ('workforce_history','workforce_contracts','workforce_economics','workforce_assignments','group_people','payroll_templates'):
                c.execute('DROP TABLE '+table)
            c.execute('PRAGMA user_version=5');c.commit()
        self.source=core.DB.parent/'backups'/core._backup()['filename']
        core.DB=self.root/'destination'/'presenze.sqlite3';core.init_db();core.setup(dict(username='webadmin',password='Password-target-2026!',name='Web',center_name='Centro web'))
        with core.connect() as c:self.admin=core.public_user(c.execute('SELECT * FROM users').fetchone())
    def tearDown(self):core.DB=self.old;core.revoke=self.old_revoke;self.tmp.cleanup()
    def test_preserves_attendance_hr_documents_and_excludes_accounts(self):
        result=import_backup(self.source);self.assertEqual(result,{'centers':1,'people':1,'entries':1,'documents':1})
        with core.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],1)
            cid=c.execute("SELECT id FROM centers WHERE name='Sede origine'").fetchone()[0]
            person=core.objects(c,'people',cid)[0];self.assertNotEqual(person['id'],self.pid)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        s=core.snapshot(self.admin,cid,'2026-10');self.assertEqual(s['summary'][0]['minutes'],360)
        d=hr.read(core,self.admin,cid,person['id']);self.assertEqual(d['profile']['fields']['iban'],'IT60X0542811101000000123456');self.assertEqual(len(d['documents']),1);self.assertEqual(len(d['profile']['tasks']),14)
        with self.assertRaisesRegex(ValueError,'già stato importato'):import_backup(self.source)
    def test_invalid_document_rolls_back_every_center(self):
        with sqlite3.connect(self.source) as c:c.execute("UPDATE hr_documents SET sha256='bad'");c.commit()
        with self.assertRaisesRegex(ValueError,'impronta'):import_backup(self.source)
        with core.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM centers').fetchone()[0],1)

if __name__=='__main__':unittest.main()
