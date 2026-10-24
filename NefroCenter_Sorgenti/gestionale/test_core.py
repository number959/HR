import copy, json, sqlite3, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
import core as app
from rules import defaults, validate_config, make_entry, duration

PASSWORD='Password-di-prova-2026!'
class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.previous=app.DB;app.DB=Path(self.temp.name)/'presenze.sqlite3';app.SESSIONS.clear();app.FAILURES.clear();app.PENDING.clear();app.init_db()
        app.setup(dict(username='admin',name='Amministratore',center_name='Centro A',password=PASSWORD))
        self.sid,self.admin=app.login(dict(username='admin',password=PASSWORD))
        with app.connect() as c:self.a=app.centers_for(c,self.admin)[0]['id']
        self.b=app.mutate(self.admin,'center_create',{'name':'Centro B','code':'CENTRO-B'})['cid']
        app.mutate(self.admin,'user_save',{'user':dict(username='operatore',name='Operatore',role='operator',centers=[self.a],active=True,password=PASSWORD)})
        app.mutate(self.admin,'user_save',{'user':dict(username='lettore',name='Lettore',role='viewer',centers=[self.a],active=True,password=PASSWORD)})
        _,self.operator=app.login(dict(username='operatore',password=PASSWORD));_,self.viewer=app.login(dict(username='lettore',password=PASSWORD))
        app.mutate(self.admin,'person',{**self.req(),'person':dict(name='Persona demo',registration='M001',role='INF',active=True)})
        self.person=app.snapshot(self.admin,self.a,'2026-10')['people'][0]['id']
    def tearDown(self):app.DB=self.previous;self.temp.cleanup()
    def req(self,cid=None,month='2026-10'):
        cid=cid or self.a;s=app.snapshot(self.admin,cid,month);return {'cid':cid,'month':month,'revision':s['center']['revision']}
    def entry(self,**extra):return dict(person_id=self.person,day='2026-10-14',slot='m',code='m',layer='actual',**extra)
    def test_no_second_setup(self):
        with self.assertRaises(PermissionError):app.setup(dict(username='evil',name='X',center_name='X',password=PASSWORD))
    def test_no_cross_center_read_or_export(self):
        for f in (lambda:app.snapshot(self.operator,self.b,'2026-10'),lambda:app.export_csv(self.operator,self.b,'2026-10')):
            with self.assertRaises(PermissionError):f()
        s=app.snapshot(self.operator,self.a,'2026-10');self.assertEqual([c['id'] for c in s['centers']],[self.a]);self.assertEqual(s['users'],[])
    def test_all_admin_routes_blocked_for_operator(self):
        for action in ('center_create','center_save','person','user_save','period_verify','close','reopen','patient','apply_rules'):
            with self.subTest(action=action),self.assertRaises(PermissionError):app.mutate(self.operator,action,self.req())
        with self.assertRaises(PermissionError):app.backup(self.operator)
        with self.assertRaises(PermissionError):app.import_confirm(self.operator,'unknown')
    def test_operator_can_enter_only_authorized_hours(self):
        with self.assertRaises(PermissionError):app.mutate(self.operator,'entry',{**self.req(),'entry':self.entry(start='06:00')})
        app.mutate(self.operator,'entry',{**self.req(),'entry':self.entry()})
        e=app.snapshot(self.admin,self.a,'2026-10')['entries'][0];self.assertEqual((e['start'],e['end'],duration(e)),('07:00','13:00',360))
    def test_forged_derived_fields_are_ignored(self):
        app.mutate(self.operator,'entry',{**self.req(),'entry':self.entry(kind='absence',credit_minutes=9999,config_version=999,updated_by='admin')})
        e=app.snapshot(self.admin,self.a,'2026-10')['entries'][0];self.assertEqual((e['kind'],e['credit_minutes'],e['updated_by']),('work',0,'operatore'))
    def test_operator_cannot_change_site_or_holiday(self):
        for fields in ({'work_site':'Centro B'},{'holiday':True}):
            with self.assertRaises(PermissionError):app.mutate(self.operator,'entry',{**self.req(),'entry':self.entry(**fields)})
    def test_reader_cannot_write(self):
        with self.assertRaises(PermissionError):app.mutate(self.viewer,'entry',{**self.req(),'entry':self.entry()})
    def test_settings_do_not_rewrite_started_month(self):
        app.mutate(self.operator,'entry',{**self.req(),'entry':self.entry()})
        cfg=app.snapshot(self.admin,self.a,'2026-10')['center']['config'];cfg['slots'][0]['start']='06:00';cfg['weekday_rate']=75
        app.mutate(self.admin,'center_save',{**self.req(),'config':cfg})
        a=app.snapshot(self.admin,self.a,'2026-10');b=app.snapshot(self.admin,self.a,'2026-11')
        self.assertEqual(a['period']['config']['slots'][0]['start'],'07:00');self.assertEqual(b['period']['config']['slots'][0]['start'],'06:00')
        self.assertEqual(app.snapshot(self.admin,self.b,'2026-11')['period']['config']['weekday_rate'],50)
        with self.assertRaises(ValueError):app.mutate(self.admin,'apply_rules',{**self.req(),'reason':'Tentativo retroattivo'})
    def test_closed_month_blocks_operator_and_admin_entries(self):
        app.mutate(self.operator,'entry',{**self.req(),'entry':self.entry()});app.mutate(self.admin,'period_verify',{**self.req(),'verified':True});app.mutate(self.admin,'close',self.req())
        for u in (self.operator,self.admin):
            with self.assertRaises(ValueError):app.mutate(u,'entry',{**self.req(),'entry':self.entry()})
        with self.assertRaises(ValueError):app.mutate(self.admin,'reopen',{**self.req(),'reason':''})
        app.mutate(self.admin,'reopen',{**self.req(),'reason':'Correzione documentata'});self.assertFalse(app.snapshot(self.admin,self.a,'2026-10')['period']['closed'])
    def test_last_admin_cannot_be_disabled(self):
        with self.assertRaises(ValueError):app.mutate(self.admin,'user_save',{'user':{**self.admin,'active':False}})
    def test_role_change_revokes_sessions(self):
        sid,_=app.login(dict(username='operatore',password=PASSWORD));app.mutate(self.admin,'user_save',{'user':{**self.operator,'role':'viewer'}})
        with self.assertRaises(app.AuthenticationError):app.session(sid)
        with self.assertRaises(PermissionError):app.mutate(self.operator,'entry',{**self.req(),'entry':self.entry()})
    def test_password_never_stored_as_plaintext_and_backup(self):
        with app.connect() as c:cred=c.execute("SELECT credential FROM users WHERE username='admin'").fetchone()[0]
        self.assertNotIn(PASSWORD,cred);self.assertTrue(app.verify_password(PASSWORD,cred));self.assertFalse(app.verify_password('wrong',cred));self.assertEqual(json.loads(cred)['iterations'],600000)
        name=app.backup(self.admin)['filename'];self.assertTrue((app.DB.parent/'backups'/name).is_file())
    def test_stale_revision_rejected(self):
        req=self.req();app.mutate(self.operator,'entry',{**req,'entry':self.entry()})
        with self.assertRaises(ValueError):app.mutate(self.operator,'entry',{**req,'entry':self.entry()})
    def test_expired_session_denied(self):
        app.SESSIONS[self.sid]['last']-=901
        with self.assertRaises(app.AuthenticationError):app.session(self.sid)
    def test_login_rate_limit(self):
        for _ in range(5):
            with self.assertRaises(app.AuthenticationError):app.login(dict(username='operatore',password='wrong'))
        with self.assertRaises(app.RateLimitError):app.login(dict(username='operatore',password=PASSWORD))
    def test_csv_formula_escaped(self):
        app.mutate(self.admin,'person',{**self.req(),'person':dict(name='=1+1',registration='M002',role='INF',active=True)})
        self.assertIn("'=1+1",app.export_csv(self.operator,self.a,'2026-10').decode('utf-8-sig'))
    def test_code_must_match_allowed_slot(self):
        with self.assertRaises(ValueError):app.mutate(self.operator,'entry',{**self.req(),'entry':dict(person_id=self.person,day='2026-10-14',slot='n',code='m',layer='actual')})
    def test_custom_absence_credit_and_shift(self):
        cfg=defaults();cfg['codes'].append(dict(id='FORMA',label='Formazione',kind='absence',credit_minutes=120,color='#008080',active=True,allowed_slots=[]))
        app.mutate(self.admin,'center_save',{**self.req(),'config':cfg})
        e=dict(person_id=self.person,day='2026-11-02',slot='m',code='FORMA',layer='actual')
        app.mutate(self.operator,'entry',{**self.req(month='2026-11'),'entry':e})
        r=app.snapshot(self.admin,self.a,'2026-11')['summary'][0];self.assertEqual((r['minutes'],r['credit_minutes'],r['absence_slots']),(0,120,1))
    def test_disabled_export_and_plan_enforced(self):
        cfg=defaults();cfg['operator_export']=False;cfg['operator_planned']=False;app.mutate(self.admin,'center_save',{**self.req(),'config':cfg})
        with self.assertRaises(PermissionError):app.export_csv(self.operator,self.a,'2026-11')
        with self.assertRaisesRegex(PermissionError,'responsabile del centro'):app.mutate(self.operator,'entry',{**self.req(month='2026-11'),'entry':dict(person_id=self.person,day='2026-11-02',slot='m',code='m',layer='planned')})

    def test_role_messages_name_the_center_manager(self):
        # The manager can verify, reopen, plan and delete: messages must not suggest admin only.
        app.mutate(self.admin,'user_save',{'user':dict(username='responsabile',name='Responsabile',role='manager',centers=[self.a],active=True,password=PASSWORD)})
        _,manager=app.login(dict(username='responsabile',password=PASSWORD))
        self.assertIn('Calendario e parametri del mese da verificare dal responsabile del centro.',app.snapshot(self.operator,self.a,'2026-10')['alerts'])
        app.mutate(manager,'entry',{**self.req(),'entry':self.entry()});app.mutate(manager,'period_verify',{**self.req(),'verified':True})
        app.mutate(manager,'close',self.req())
        with self.assertRaisesRegex(ValueError,'riapertura motivata del responsabile del centro'):app.mutate(self.operator,'entry',{**self.req(),'entry':{**self.entry(),'day':'2026-10-15'}})
        app.mutate(manager,'reopen',{**self.req(),'reason':'Correzione autorizzata'})
        self.assertFalse(app.snapshot(manager,self.a,'2026-10')['period']['closed'])

    def test_overlap_explicit_identity_across_centers(self):
        app.mutate(self.admin,'person',{**self.req(self.b),'person':dict(name='Persona demo B',registration='M001',role='INF',active=True)})
        second=app.snapshot(self.admin,self.b,'2026-10')['people'][0]['id']
        import workforce
        with app.connect() as c:
            target=workforce.ensure_person(c,self.a,self.person)
            source=workforce.ensure_person(c,self.b,second)
        workforce.mutate(app,self.admin,'workforce_link',dict(cid=self.b,pid=second,assignment_version=source['version'],global_id=target['global_id'],target_version=1,reason='Identità verificata'))
        app.mutate(self.admin,'entry',{**self.req(self.b),'entry':dict(person_id=second,day='2026-10-14',slot='m',code='m',layer='actual')})
        with self.assertRaises(ValueError):app.mutate(self.operator,'entry',{**self.req(),'entry':self.entry()})
    def test_personal_agreement_validated(self):
        p=app.snapshot(self.admin,self.a,'2026-10')['people'][0]
        pay=dict(weekday_rate=60,holiday_rate=80,fixed_deduction=0,ccnl_rate=120,pay_mode='all')
        app.mutate(self.admin,'person',{**self.req(),'person':{**p,'pay_override':pay}})
        self.assertEqual(app.snapshot(self.admin,self.a,'2026-10')['people'][0]['pay_override'],pay)
        with self.assertRaises(ValueError):app.mutate(self.admin,'person',{**self.req(),'person':{**p,'pay_override':{**pay,'weekday_rate':-1}}})

    def test_permission_revocation_immediate_on_started_month(self):
        app.mutate(self.operator,'entry',{**self.req(),'entry':self.entry()})
        cfg=defaults();cfg['operator_export']=False;cfg['operator_delete']=False
        app.mutate(self.admin,'center_save',{**self.req(),'config':cfg})
        with self.assertRaises(PermissionError):app.export_csv(self.operator,self.a,'2026-10')
        entry=app.snapshot(self.operator,self.a,'2026-10')['entries'][0]
        with self.assertRaisesRegex(PermissionError,'responsabile del centro'):app.mutate(self.operator,'delete',{**self.req(),'id':entry['id']})

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.previous=app.DB;app.DB=Path(self.temp.name)/'presenze.sqlite3'
        app.init_db();self.directory=app.DB.parent/'backups'
        for path in self.directory.iterdir():path.unlink()
    def tearDown(self):app.DB=self.previous;self.temp.cleanup()
    def test_daily_backup_ignores_incomplete_files_and_directories(self):
        today=app.date.today().strftime('%Y%m%d')
        (self.directory/('presenze_'+today+'_000000_000000.sqlite3')).mkdir()
        (self.directory/('presenze_'+today+'_000000_000001.sqlite3')).write_bytes(b'incomplete')
        (self.directory/('presenze_'+today+'_000000_000002.sqlite3')).symlink_to(app.DB)
        (self.directory/('presenze_'+today+'_000000_000003.sqlite3.partial')).write_bytes(b'incomplete')
        (self.directory/('presenze_'+today+'_other.sqlite3')).write_bytes(b'SQLite format 3\x00')
        with patch.object(app,'_backup',wraps=app._backup) as backup:
            app.init_db();backup.assert_called_once()
        completed=[path for path in self.directory.iterdir() if path.is_file() and not path.is_symlink() and path.stat().st_size>16]
        self.assertEqual(len(completed),1)
        with sqlite3.connect(completed[0]) as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        with patch.object(app,'_backup',wraps=app._backup) as backup:
            app.init_db();backup.assert_not_called()

class RuleTests(unittest.TestCase):
    def test_default_valid(self):self.assertEqual(validate_config(defaults())['min_rest_hours'],11)
    def test_invalid_config_rejected(self):
        for key,value in [('weekday_rate',-1),('min_rest_hours',float('nan')),('csv_separator','|'),('operator_delete','yes')]:
            cfg=defaults();cfg[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_config(cfg)
    def test_overnight_overlap(self):
        cfg=defaults();p=dict(id='a');raw=dict(id='one',person_id='a',day='2026-10-31',slot='n',code='n',layer='actual');old,_=make_entry(raw,cfg,p,'A','admin',[])
        raw=dict(id='two',person_id='a',day='2026-11-01',slot='m',code='m',layer='actual',start='06:30',end='12:30')
        with self.assertRaises(ValueError):make_entry(raw,cfg,p,'A','admin',[old])

if __name__=='__main__':unittest.main(verbosity=2)
