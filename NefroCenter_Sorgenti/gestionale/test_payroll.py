"""The consultant file must match its preview, preserve missing data and obey HR scope."""
import copy
import csv
import io
import json
import unittest
import zipfile
from xml.etree import ElementTree

import core
import payroll
import workforce
from test_analytics import StatisticsFixture
from test_core import PASSWORD


class PayrollTests(StatisticsFixture):
    def setUp(self):
        super().setUp()
        workforce.init(core)
        payroll.init(core)

    def config(self, confirmed=True, **changes):
        current = payroll.read(core, self.admin, self.a)
        cfg = copy.deepcopy(current['config'])
        if confirmed:
            cfg.update(status='confirmed', confirmation_note='Specifiche del consulente verificate il 01/10/2026')
        cfg['causes'].update(m='ORD', p='ORD', F='FER', R='RIP')
        cfg.update(changes)
        return cfg, current['version']

    def save(self, confirmed=True, **changes):
        cfg, version = self.config(confirmed, **changes)
        payroll.save(core, self.admin, {'cid': self.a, 'expected_version': version, 'config': cfg})
        return cfg

    def preview(self, user=None, **changes):
        return payroll.preview(core, user or self.admin, changes.get('cid', self.a),
                               changes.get('first', '2026-10'), changes.get('last', '2026-10'))

    def download(self, preview, user=None, format='csv'):
        return payroll.export(core, user or self.admin, preview['cid'], preview['first'],
                              preview['last'], format, preview['fingerprint'])

    @staticmethod
    def records(preview):
        return [dict(zip([c['field'] for c in preview['columns']], r)) for r in preview['rows']]

    def make_user(self, username, role, centers):
        core.mutate(self.admin, 'user_save', {'user': dict(username=username, name=username,
            role=role, centers=centers, active=True, password=PASSWORD)})
        with core.connect() as c:
            return core.public_user(c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone())

    def test_default_is_draft_and_blocks_download_until_consultant_confirmation(self):
        self.entry()
        self.assertEqual(payroll.read(core, self.admin, self.a)['version'], 0)
        p = self.preview()
        self.assertFalse(p['can_download'])
        self.assertIn('unconfirmed_template', {i['code'] for i in p['issues']})
        with self.assertRaisesRegex(ValueError, 'bloccanti'):
            self.download(p)
        self.save()
        p = self.preview()
        self.assertTrue(p['can_download'])
        self.assertIn('open_months', {i['code'] for i in p['issues']})
        self.assertTrue(self.download(p).startswith(b'\xef\xbb\xbf'))

    def test_versions_are_immutable_and_stale_writes_rejected(self):
        cfg, version = self.config()
        payroll.save(core, self.admin, {'cid':self.a, 'expected_version':version, 'config':cfg})
        with self.assertRaisesRegex(ValueError, 'cambiato'):
            payroll.save(core, self.admin, {'cid':self.a, 'expected_version':version, 'config':cfg})
        self.save(name='Nuovo schema verificato')
        self.assertEqual([x['version'] for x in payroll.read(core, self.admin, self.a)['history']], [2, 1])
        with core.connect() as c:
            original = json.loads(c.execute('SELECT data FROM payroll_templates WHERE cid=? AND version=1', (self.a,)).fetchone()[0])
        self.assertEqual(original['name'], cfg['name'])

    def test_missing_hours_stay_blank_and_pending_actual_is_blocking(self):
        self.entry(start='', end='')
        self.entry(day='2026-10-05', layer='planned')
        self.save()
        p = self.preview()
        self.assertIsNone(p['summary']['known_minutes'])
        self.assertEqual((p['summary']['missing_hours'], p['summary']['pending_actual']), (1, 1))
        self.assertIsNone(self.records(p)[0]['worked_minutes'])
        self.assertIsNone(self.records(p)[0]['worked_hours'])
        self.assertTrue({'missing_hours','pending_actual'} <= {i['code'] for i in p['issues']})
        with self.assertRaises(ValueError):
            self.download(p)
        self.entry(day='2026-10-05', kind='absence', code='F', start='', end='')
        self.assertEqual(self.preview()['summary']['pending_actual'], 0)

    def test_hours_and_absence_credits_are_separate_and_absence_days_not_duplicated(self):
        self.entry(start='22:00', end='04:30', overnight=True, pause=30)
        for slot in ('m','p'):
            self.entry(day='2026-10-06', slot=slot, kind='absence', code='F',
                       start='', end='', credit_minutes=120)
        self.save()
        p = self.preview(); rows = self.records(p)
        self.assertEqual((p['summary']['known_minutes'], p['summary']['absence_slots'], p['summary']['absence_days']), (360, 2, 1))
        self.assertEqual(rows[0]['worked_hours'], 6)
        self.assertEqual([r['absence_days'] for r in rows[1:]], [1, 0])
        self.assertEqual([r['credited_minutes'] for r in rows[1:]], [120, 120])
        self.assertTrue(all(r['worked_hours'] is None for r in rows[1:]))

    def test_duplicate_registrations_unmapped_cause_and_overlap_block(self):
        self.entry()
        self.entry(slot='p', code='p', start='12:00', end='18:00')
        with core.connect() as c:
            p = core.objects(c, 'people', self.a)[0]
            core.put(c, 'people', self.a, {**p, 'id':'other', 'name':'Altra persona'})
            c.commit()
        self.entry(person_id='other', code='UNKNOWN')
        self.save()
        p = self.preview()
        self.assertTrue({'duplicate_registration','unmapped_cause','overlap'} <= {i['code'] for i in p['issues']})
        self.assertFalse(p['can_download'])

    def test_preview_fingerprint_rejects_data_or_model_changes(self):
        entry = self.entry()
        self.save()
        p = self.preview()
        self.download(p)
        with core.connect() as c:
            core.put(c, 'entries', self.a, {**entry, 'end':'14:00'}); c.commit()
        with self.assertRaisesRegex(ValueError, 'cambiati'):
            self.download(p)
        p = self.preview()
        self.save(name='Modello aggiornato')
        with self.assertRaisesRegex(ValueError, 'cambiati'):
            self.download(p)
        p = self.preview(); raw = self.download(p)
        with core.connect() as c:
            event = json.loads(c.execute("SELECT after_data FROM audit WHERE action='Esportazione paghe' ORDER BY id DESC LIMIT 1").fetchone()[0])
        self.assertEqual(event['fingerprint'], p['fingerprint'])
        self.assertEqual(event['version'], 2)
        self.assertEqual(event['rows'], 1)
        self.assertTrue(raw)

    def test_csv_escapes_formulas_and_excel_preserves_matricola_as_text(self):
        self.entry(end='13:30')
        with core.connect() as c:
            person = core.objects(c, 'people', self.a)[0]
            core.put(c, 'people', self.a, {**person, 'name':'=HYPERLINK("x")'}); c.commit()
        self.save(registrations={self.person:'000123'})
        p = self.preview()
        csv_rows = list(csv.reader(io.StringIO(self.download(p).decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(csv_rows[1][2], '000123')
        self.assertEqual(csv_rows[1][3], '\'=HYPERLINK("x")')
        self.assertEqual(csv_rows[1][8], '6,5')
        raw = self.download(p, format='xlsx')
        ns = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            sheet = ElementTree.fromstring(z.read('xl/worksheets/sheet1.xml'))
            strings = ElementTree.fromstring(z.read('xl/sharedStrings.xml'))
        self.assertEqual(sheet.find('.//s:c[@r="C2"]', ns).attrib['t'], 's')
        self.assertEqual(sheet.find('.//s:c[@r="I2"]/s:v', ns).text, '6.5')
        self.assertFalse(sheet.findall('.//s:f', ns))
        self.assertIn('000123', ''.join(strings.itertext()))

    def test_permissions_scope_and_fresh_role_are_checked_at_each_operation(self):
        self.entry();self.save();p=self.preview()
        manager=self.make_user('manager','manager',[self.a])
        hruser=self.make_user('hrcentral','hr',[])
        self.assertEqual(self.preview(manager)['summary']['rows'],1)
        self.assertEqual(payroll.read(core,hruser,self.b)['cid'],self.b)
        for user in (self.operator,self.viewer):
            for operation in (lambda:payroll.read(core,user,self.a),lambda:self.preview(user),lambda:self.download(p,user)):
                with self.assertRaises(PermissionError):operation()
        with self.assertRaises(PermissionError):payroll.read(core,manager,self.b)
        with core.connect() as c:
            c.execute("UPDATE users SET role='viewer' WHERE id=?",(hruser['id'],));c.commit()
        with self.assertRaises(PermissionError):self.download(p,hruser)

    def test_contract_fields_follow_intramonth_effective_dates(self):
        self.entry(day='2026-10-15');self.entry(day='2026-10-16')
        for start,end,role,hours in [('2026-10-01','2026-10-15','INF',40),('2026-10-16','','MED',20)]:
            with core.connect() as c:
                assignment=workforce.ensure_person(c,self.a,self.person)
            workforce.mutate(core,self.admin,'workforce_contract',{
                'cid':self.a,'pid':self.person,'assignment_version':assignment['version'],
                'version':0,'effective_from':start,'effective_to':end,'reason':'Decorrenza contrattuale verificata',
                'data':dict(role=role,contract_type='Dipendente',ccnl='CCNL demo',level='D',weekly_hours=hours,part_time_percent=hours/40*100,note='')})
        cfg,_=self.config()
        cfg['columns'] += [{'field':field,'label':payroll.FIELDS[field][0]} for field in ('role','weekly_hours','part_time_percent')]
        self.save(columns=cfg['columns'])
        rows=self.records(self.preview())
        self.assertEqual([(r['role'],r['weekly_hours'],r['part_time_percent']) for r in rows],[('INF',40,100),('MED',20,50)])
        self.assertTrue(self.preview()['can_download'])

    def test_required_historical_contract_is_not_invented(self):
        self.entry()
        cfg,_=self.config();cfg['columns'].append({'field':'weekly_hours','label':'Ore contrattuali'})
        self.save(columns=cfg['columns'])
        p=self.preview()
        self.assertIsNone(self.records(p)[0]['weekly_hours'])
        self.assertIn('missing_contract_value',{i['code'] for i in p['issues']})
        self.assertFalse(p['can_download'])

    def test_invalid_model_and_period_are_rejected(self):
        cfg,version=self.config()
        invalid=[{**cfg,'confirmation_note':'ok'}, {**cfg,'columns':cfg['columns'][1:]},
                 {**cfg,'columns':cfg['columns']+[cfg['columns'][0]]},
                 {**cfg,'registrations':{'other-center-person':'MAT'}}, {**cfg,'delimiter':'|'}]
        for candidate in invalid:
            with self.subTest(config=candidate),self.assertRaises(ValueError):
                payroll.save(core,self.admin,{'cid':self.a,'expected_version':version,'config':candidate})
        for first,last in [('2026-10','2026-09'),('2026-13','2026-13'),('2024-01','2026-01')]:
            with self.assertRaises(ValueError):self.preview(first=first,last=last)
        with self.assertRaises(ValueError):self.preview(cid='all')


if __name__ == '__main__':
    unittest.main()
