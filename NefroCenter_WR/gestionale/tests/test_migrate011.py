"""Migrazione dalla 0.11: tutto o niente, archivio di origine intatto, accessi conservati, servizi spenti."""
import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from support import ORIGIN, Client, Clock
import legacy011

from wr import app as factory, approvals, migrate011, security
from wr.auth import Auth


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class MigrationCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='wr-migra-'))
        self.legacy_key = self.tmp / 'chiave-011.key'
        Auth.create_key(self.legacy_key)
        self.source = self.tmp / 'presenze.sqlite3'
        self.clock = Clock()
        legacy011.build(self.source, legacy_key_path=self.legacy_key, now=self.clock())
        self.key = self.tmp / 'wr.key'
        Auth.create_key(self.key)
        self.data = self.tmp / 'nuovo'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def migrate(self, legacy_key=True):
        return migrate011.run(self.source, self.data, self.key, legacy_key=self.legacy_key if legacy_key else None,
                              clock=self.clock)

    def query(self, sql, *args):
        con = sqlite3.connect(self.data / 'wr.sqlite3')
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args)]
        finally:
            con.close()


class MigrationTests(MigrationCase):
    def test_source_untouched_and_counts_reported(self):
        before = file_hash(self.source)
        report = self.migrate()
        self.assertEqual(file_hash(self.source), before)
        s = report['summary']
        self.assertEqual(s['importati']['centers'], 2)
        self.assertEqual(s['importati']['people'], 4)
        self.assertEqual(s['importati']['entries_duplicates'], 1)
        self.assertEqual(s['conteggi_wr']['entries'], 8)
        self.assertTrue((self.data / 'migrazione-011.json').exists())
        saved = json.loads((self.data / 'migrazione-011.json').read_text())
        self.assertNotIn('activation_codes', saved)
        self.assertEqual(self.query("SELECT value FROM meta WHERE key='migration_source_sha256'")[0]['value'], before)
        self.assertTrue(list((self.data / 'backups').glob('*.sqlite3')))

    def test_refuses_existing_archive_and_wrong_files(self):
        self.migrate()
        before = file_hash(self.data / 'wr.sqlite3')
        with self.assertRaisesRegex(migrate011.MigrationError, 'esiste già un archivio'):
            self.migrate()
        self.assertEqual(file_hash(self.data / 'wr.sqlite3'), before)
        with self.assertRaisesRegex(migrate011.MigrationError, 'già un archivio NefroCenter WR'):
            migrate011.run(self.data / 'wr.sqlite3', self.tmp / 'altro', self.key)
        old = self.tmp / 'vecchio.sqlite3'
        shutil.copy(self.source, old)
        con = sqlite3.connect(old)
        con.execute('PRAGMA user_version=7')
        con.commit()
        con.close()
        with self.assertRaisesRegex(migrate011.MigrationError, 'precedente alla 0.11'):
            migrate011.run(old, self.tmp / 'altro', self.key)
        self.assertFalse((self.tmp / 'altro' / 'wr.sqlite3').exists())

    def test_all_or_nothing(self):
        con = sqlite3.connect(self.source)
        cfg = json.loads(con.execute("SELECT config FROM centers WHERE code='DUE'").fetchone()[0])
        cfg['slots'] = []
        con.execute("UPDATE centers SET config=? WHERE code='DUE'", (json.dumps(cfg),))
        con.commit()
        con.close()
        with self.assertRaisesRegex(migrate011.MigrationError, 'Centro Due: parametri della versione 1 non validi'):
            self.migrate()
        self.assertFalse((self.data / 'wr.sqlite3').exists())

    def test_months_keep_their_parameters(self):
        self.migrate()
        months = {(r['center_id'][-1], r['month']): r for r in self.query('SELECT * FROM months')}
        self.assertEqual(months[('1', '2026-09')]['rules_version'], 1)
        self.assertTrue(months[('1', '2026-09')]['closed'])
        self.assertEqual(months[('1', '2026-10')]['rules_version'], 2)
        versions = self.query("SELECT version, data FROM center_configs WHERE center_id=? ORDER BY version", legacy011.C1)
        self.assertEqual([v['version'] for v in versions], [1, 2])
        self.assertEqual(json.loads(versions[1]['data'])['min_rest_hours'], 12)
        self.assertEqual(self.query('SELECT config_version FROM centers WHERE id=?', legacy011.C1)[0]['config_version'], 2)

    def test_entries_sites_imports_and_duplicates(self):
        self.migrate()
        rows = {r['id']: r for r in self.query('SELECT * FROM entries')}
        self.assertEqual(rows['e1']['site'], '')
        self.assertEqual(rows['e3']['site'], 'Sede esterna Napoli Est')
        imported = rows['e6']
        self.assertEqual(imported['site'], 'Sede esterna da specificare')
        self.assertIn('Colore', imported['review'])
        self.assertEqual(imported['source'], 'excel:AB12')
        self.assertEqual(imported['pause'], 0)
        self.assertNotIn('e7', rows)
        self.assertEqual(rows['e8']['start'], '08:00')
        self.assertEqual(rows['e2']['kind'], 'absence')

    def test_people_identities_and_profiles(self):
        self.migrate()
        people = {r['id']: r for r in self.query('SELECT * FROM people')}
        self.assertEqual(people[legacy011.ANNA1]['identity_id'], people[legacy011.ANNA2]['identity_id'])
        self.assertFalse(people[legacy011.LUCA]['active'])
        self.assertEqual(json.loads(people[legacy011.MARCO]['pay_override'])['pay_mode'], 'all')
        profile = self.query('SELECT * FROM profiles WHERE person_id=?', legacy011.ANNA1)[0]
        self.assertEqual(json.loads(profile['fields'])['first_name'], 'Anna')
        self.assertEqual(json.loads(profile['custom']), {'badge_extra': 'B-12'})
        tasks = self.query('SELECT * FROM onboarding_tasks WHERE person_id=? ORDER BY position', legacy011.ANNA1)
        self.assertEqual([t['status'] for t in tasks], ['done', 'todo'])
        self.assertEqual(tasks[1]['due'], '2026-09-01')
        self.assertEqual(len(self.query('SELECT * FROM profile_history')), 2)
        docs = {d['id']: d for d in self.query('SELECT id, mime, size, sha256 FROM documents')}
        self.assertEqual(docs['doc1']['mime'], 'application/pdf')
        self.assertEqual(docs['doc2']['mime'], 'image/png')
        self.assertEqual(self.query("SELECT status FROM document_reviews WHERE document_id='doc1'")[0]['status'], 'verified')
        self.assertEqual(self.query("SELECT status FROM document_reviews WHERE document_id='doc2'")[0]['status'], 'received')

    def test_agreements_saved_only_and_segments(self):
        report = self.migrate()
        rows = self.query('SELECT * FROM agreements ORDER BY month')
        self.assertEqual([(r['month'], r['person_id']) for r in rows], [('2026-09', legacy011.ANNA1), ('2026-10', legacy011.MARCO)])
        self.assertEqual(report['summary']['importati']['agreements_proposals_recalculated'], 1)
        seg = json.loads(rows[1]['data'])['segments'][0]
        self.assertEqual((seg['valid_from'], seg['valid_to']), ('2026-10-01', '2026-10-31'))
        self.assertEqual(rows[0]['source'], 'Accordo confermato con la persona')

    def test_services_arrive_switched_off(self):
        report = self.migrate()
        mail = json.loads(self.query('SELECT data FROM mail_settings')[0]['data'])
        self.assertFalse(mail['enabled'])
        reminders = json.loads(self.query('SELECT data FROM reminder_settings')[0]['data'])
        self.assertFalse(reminders['enabled'])
        self.assertEqual(reminders['approved_routes'], {})
        self.assertTrue(any('posta' in w for w in report['summary']['avvisi']))
        self.assertTrue(any('promemoria' in w for w in report['summary']['avvisi']))
        recipients = {r['id']: r for r in self.query('SELECT * FROM mail_recipients')}
        self.assertEqual(recipients['r2']['status'], 'uncertain')
        self.assertEqual(json.loads(recipients['r1']['data'])['center_id'], legacy011.C1)

    def test_approval_and_substitution_fingerprints_recomputed(self):
        self.migrate()
        application = factory.create(self.data, origin=ORIGIN, key_file=self.key, dev=True, clock=self.clock)
        with application.db.read() as con:
            current = approvals.fingerprint(con, legacy011.C1, '2026-09')
            stored = con.execute("SELECT fingerprint, status FROM approvals WHERE month='2026-09'").fetchone()
        self.assertEqual(stored['status'], 'hr_approved')
        self.assertEqual(stored['fingerprint'], current)
        self.assertEqual(len(self.query('SELECT * FROM approval_history')), 3)
        sub = self.query('SELECT * FROM substitutions')[0]
        self.assertEqual(sub['person_id'], legacy011.ANNA2)
        self.assertNotEqual(sub['fingerprint'], 'impronta-0.11')

    def test_workforce_departures_payroll(self):
        self.migrate()
        self.assertEqual(self.query('SELECT kind FROM workforce_history ORDER BY id')[0]['kind'], 'contract')
        self.assertEqual(self.query('SELECT kind FROM workforce_history ORDER BY id')[1]['kind'], 'apply')
        self.assertEqual(self.query('SELECT person_id FROM contracts')[0]['person_id'], legacy011.ANNA1)
        dep = self.query('SELECT * FROM departures')[0]
        self.assertEqual(dep['person_id'], legacy011.LUCA)
        self.assertEqual(json.loads(dep['tasks'])[0]['id'], 'badge')
        self.assertEqual(self.query('SELECT asset_key FROM equipment')[0]['asset_key'], 'chiave 7')
        self.assertEqual(sorted(r['kind'] for r in self.query('SELECT kind FROM process_history')), ['departure', 'equipment'])
        template = json.loads(self.query('SELECT data FROM payroll_templates')[0]['data'])
        self.assertEqual(template['registrations'], {legacy011.MARCO: 'PAGHE-2'})


class AccessTests(MigrationCase):
    def login(self, application, username, code_secret=None, password=legacy011.PASSWORD):
        c = Client(application)
        c.ok('GET', '/api/session')
        c.ok('POST', '/api/session/login', {'username': username, 'password': password})
        if code_secret:
            self.clock.advance(31)
            c.ok('POST', '/api/session/verify', {'code': security.totp_code(code_secret, int(self.clock() // 30))})
        return c

    def test_password_and_authenticator_still_work(self):
        report = self.migrate()
        self.assertEqual(report['activation_codes'], [])
        application = factory.create(self.data, origin=ORIGIN, key_file=self.key, dev=True, clock=self.clock)
        c = self.login(application, 'admin011', 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP')
        me = c.ok('GET', '/api/me')
        self.assertEqual(me['user']['role'], 'admin')
        self.assertEqual(len(me['centers']), 2)
        data = c.ok('GET', f'/api/attendance/{legacy011.C1}/2026-10')
        self.assertEqual(data['state']['rules_version'], 2)
        recovery = Client(application)
        recovery.ok('GET', '/api/session')
        recovery.ok('POST', '/api/session/login', {'username': 'admin011', 'password': legacy011.PASSWORD})
        recovery.ok('POST', '/api/session/verify', {'code': 'ABCD-1234-ABCD-1234', 'recovery': True})

    def test_without_legacy_key_new_activation_codes(self):
        report = self.migrate(legacy_key=False)
        self.assertEqual([u for u, _ in report['activation_codes']], ['admin011'])
        self.assertEqual(report['summary']['account_da_riattivare'], ['admin011'])
        application = factory.create(self.data, origin=ORIGIN, key_file=self.key, dev=True, clock=self.clock)
        code = report['activation_codes'][0][1]
        c = Client(application)
        c.ok('GET', '/api/session')
        state = c.ok('POST', '/api/session/activation', {'username': 'admin011', 'activation': code})
        self.assertEqual(state['stage'], 'enroll')

    def test_pending_activation_is_kept(self):
        self.migrate()
        application = factory.create(self.data, origin=ORIGIN, key_file=self.key, dev=True, clock=self.clock)
        c = Client(application)
        c.ok('GET', '/api/session')
        state = c.ok('POST', '/api/session/activation', {'username': 'comp011', 'activation': 'codice-attivazione-011'})
        self.assertEqual(state['stage'], 'enroll')
        assigned = {r['center_id'] for r in self.query("SELECT center_id FROM user_centers WHERE user_id='u4'")}
        self.assertEqual(assigned, {legacy011.C1, legacy011.C2})


if __name__ == '__main__':
    unittest.main()
