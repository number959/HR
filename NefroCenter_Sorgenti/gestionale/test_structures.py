"""Rubrica strutture: permessi, input, concorrenza e fascicoli collegati."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import core
import hr
import structures


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = core.DB
        core.DB = Path(self.tmp.name) / 'data' / 'presenze.sqlite3'
        core.init_db()
        structures.init(core)
        core.setup(dict(username='admin', name='Amministratore', center_name='Struttura Uno',
                        password='Password-test-2026!'))
        with core.connect() as c:
            self.admin = core.public_user(c.execute("SELECT * FROM users WHERE username='admin'").fetchone())
            self.one = core.centers_for(c, self.admin)[0]['id']
        self.two = core.mutate(self.admin, 'center_create', {'name': 'Struttura Due', 'code': 'DUE'})['cid']
        self.hr = self.user('centralehr', 'hr', [])
        self.manager = self.user('responsabile', 'manager', [self.one])
        self.operator = self.user('operatore', 'operator', [self.one])
        self.viewer = self.user('lettore', 'viewer', [self.one])

    def tearDown(self):
        core.DB = self.previous
        self.tmp.cleanup()

    def user(self, username, role, centers):
        # Authentication itself is covered elsewhere; keep these permission tests fast.
        with core.connect() as c:
            credential = c.execute('SELECT credential FROM users WHERE id=?', (self.admin['id'],)).fetchone()[0]
            c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',
                      (core.uid(), username, username, role, core.dump(centers), 1, credential))
            c.commit()
            return core.public_user(c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone())

    def save(self, cid=None, user=None, version=0, **fields):
        return structures.save(core, user or self.admin,
                               dict(cid=cid or self.one, version=version, fields=fields))['structure']

    def test_blank_records_and_field_definitions_for_all_authorized_centers(self):
        result = structures.read(core, self.hr, 'all')
        self.assertEqual({self.one, self.two}, {s['cid'] for s in result['structures']})
        self.assertEqual(set(structures.FIELDS), {f['key'] for f in result['fields']})
        for item in result['structures']:
            self.assertEqual(item['version'], 0)
            self.assertEqual(item['fields'], {key: '' for key in structures.FIELDS})
        new = core.mutate(self.admin, 'center_create', {'name': 'Nuova Struttura', 'code': 'TRE'})['cid']
        self.assertIn(new, {s['cid'] for s in structures.read(core, self.hr)['structures']})

    def test_hr_and_assigned_manager_can_save_without_changing_center_configuration(self):
        with core.connect() as c:
            before = core.center(c, self.one)
        first = self.save(user=self.hr, legal_name='Società Centro Uno', hr_email='hr@example.test')
        updated = self.save(user=self.manager, version=first['version'],
                            legal_name='Società Centro Uno', hr_email='ufficio.hr+uno@example.test')
        self.assertEqual(updated['version'], 2)
        self.assertEqual(structures.read(core, self.hr, self.one)['structure'], updated)
        with core.connect() as c:
            self.assertEqual(core.center(c, self.one), before)
            audit = c.execute("SELECT * FROM audit WHERE action='Scheda struttura salvata' ORDER BY id DESC").fetchone()
            self.assertEqual(audit['username'], self.manager['username'])
            self.assertEqual(json.loads(audit['before_data'])['fields']['hr_email'], 'hr@example.test')
            self.assertEqual(json.loads(audit['after_data']), updated)

    def test_manager_scope_cannot_be_bypassed_and_operator_viewer_cannot_read(self):
        self.save(cid=self.two, email='riservata@example.test')
        self.assertEqual([self.one], [s['cid'] for s in structures.read(core, self.manager)['structures']])
        for call in (lambda: structures.read(core, self.manager, self.two),
                     lambda: self.save(cid=self.two, user=self.manager)):
            with self.assertRaises(PermissionError):
                call()
        for user in (self.operator, self.viewer):
            for cid in (None, 'all', self.one):
                with self.subTest(user=user['role'], cid=cid), self.assertRaises(PermissionError):
                    structures.read(core, user, cid)
            with self.assertRaises(PermissionError):
                self.save(user=user)
            self.assertNotIn('structure_profiles', core.dump(core.snapshot(user, self.one, '2026-10')))

    def test_stale_users_recheck_role_assignment_and_active_status(self):
        with core.connect() as c:
            c.execute('UPDATE users SET centers=? WHERE id=?', (core.dump([self.two]), self.manager['id']))
            c.commit()
        self.assertEqual([self.two], [s['cid'] for s in structures.read(core, self.manager)['structures']])
        with self.assertRaises(PermissionError):
            self.save(user=self.manager)
        with core.connect() as c:
            c.execute("UPDATE users SET role='viewer',centers=? WHERE id=?", (core.dump([self.one]), self.hr['id']))
            c.commit()
        with self.assertRaises(PermissionError):
            structures.read(core, self.hr)
        with core.connect() as c:
            c.execute('UPDATE users SET active=0 WHERE id=?', (self.admin['id'],))
            c.commit()
        with self.assertRaises(core.AuthenticationError):
            self.save()

    def test_email_validation_rejects_headers_multiple_recipients_and_invalid_domains(self):
        invalid = ['a@example.test\r\nBcc: other@example.test', '\na@example.test',
                   'a@example.test\r', 'a@example.test,b@example.test', 'a@example.test;b@example.test',
                   'Persona <a@example.test>', 'a@', '@example.test', 'a@example',
                   'a@-example.test', '.a@example.test', 'a..b@example.test', 'a b@example.test',
                   'a@exam ple.test', 'a@exam_ple.test', 'a\x00@example.test']
        for key in ('email', 'hr_email', 'admin_email', 'pec'):
            for value in invalid:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.save(**{key: value})
        self.assertEqual(self.save(email='  ufficio+uno@example.test  ')['fields']['email'],
                         'ufficio+uno@example.test')

    def test_websites_accept_only_valid_http_https_without_credentials(self):
        invalid = ['javascript:alert(1)', 'data:text/html,ciao', 'ftp://example.test',
                   '//example.test', 'https://', 'https://user:password@example.test',
                   'https://example.test:invalid', 'https://example.test:70000',
                   'https://example.test:0', 'https://exam ple.test',
                   'https://example.test\r\nHeader: x', 'https://example.test\\@other.test',
                   'https://[invalid', 'https://-example.test']
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.save(website=value)
        for value in ('https://example.test/path?q=1#contact', 'http://intranet:8080', 'https://[::1]:443/'):
            with self.subTest(valid=value):
                self.assertEqual(structures.validate_fields({'website': value})['website'], value)

    def test_field_limits_types_and_control_characters_are_enforced(self):
        for key, limit in structures.FIELDS.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.save(**{key: 'x' * (limit + 1)})
        for fields in ({'unknown': 'x'}, {'phone': 123}, {'legal_name': 'Società\x00'},
                       {'contact_name': 'Nome\nCognome'}, {'notes': 'Nota\x7f'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                structures.validate_fields(fields)
        for fields in (None, [], 'test'):
            with self.assertRaises(ValueError):
                structures.validate_fields(fields)
        self.assertEqual(self.save(notes='Prima riga\nSeconda riga')['fields']['notes'],
                         'Prima riga\nSeconda riga')

    def test_conflicting_edits_do_not_overwrite_or_create_audit_events(self):
        first = self.save(email='first@example.test')
        for version in (0, True, '1', None, -1):
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.save(version=version, email='lost@example.test')
        self.assertEqual(structures.read(core, self.admin, self.one)['structure'], first)
        with core.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM audit WHERE action='Scheda struttura salvata'").fetchone()[0], 1)

    def test_two_simultaneous_writers_keep_one_confirmed_version(self):
        self.save()
        ready = threading.Barrier(2)
        def write(address):
            ready.wait(timeout=5)
            try:
                return self.save(version=1, email=address)
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(write, ['first@example.test', 'second@example.test']))
        self.assertEqual(sum(result is not None for result in results), 1)
        final = structures.read(core, self.admin, self.one)['structure']
        self.assertEqual(final['version'], 2)
        self.assertEqual(final, next(result for result in results if result is not None))

    def test_shared_structure_is_live_in_hr_without_copies_or_nested_connections(self):
        with core.connect() as c:
            revision = core.center(c, self.one)['revision']
        pid = hr.save(core, self.manager,
                      dict(cid=self.one, revision=revision, version=0, name='Persona Demo',
                           role='INF', registration='DEMO1', fields={}, custom={}))['pid']
        first = hr.read(core, self.hr, self.one, pid)
        self.assertEqual(first['structure']['version'], 0)
        saved = self.save(hr_email='ufficio@example.test', legal_name='Società Esempio')
        original_connect = core.connect
        with patch.object(core, 'connect', wraps=original_connect) as connect:
            profile = hr.read(core, self.hr, self.one, pid)
            self.assertEqual(connect.call_count, 1)
        self.assertEqual(profile['structure'], saved)
        self.assertEqual(profile['profile'], first['profile'])
        with core.connect() as c:
            self.assertNotIn('ufficio@example.test', c.execute('SELECT data FROM hr_profiles WHERE cid=? AND pid=?', (self.one, pid)).fetchone()[0])
        with self.assertRaises(PermissionError):
            hr.read(core, self.operator, self.one, pid)
        self.assertEqual(self.save(version=1, hr_email='nuovo@example.test')['fields']['hr_email'],
                         hr.read(core, self.hr, self.one, pid)['structure']['fields']['hr_email'])

    def test_initialization_is_idempotent_and_center_name_remains_authoritative(self):
        saved = self.save(legal_name='Società Centro Uno')
        structures.init(core)
        self.assertEqual(structures.read(core, self.admin, self.one)['structure'], saved)
        with core.connect() as c:
            c.execute('UPDATE centers SET name=?,code=? WHERE id=?', ('Nuovo nome', 'NUOVO', self.one))
            c.commit()
        renamed = structures.read(core, self.admin, self.one)['structure']
        self.assertEqual((renamed['name'], renamed['code']), ('Nuovo nome', 'NUOVO'))
        self.assertEqual(renamed['fields'], saved['fields'])


if __name__ == '__main__':
    unittest.main()
