"""Monthly gates must enforce roles, same-data approval and atomic freezes."""
import copy
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
import core
import approvals
import test_structures as fixtures


class ApprovalTests(unittest.TestCase):
    user = fixtures.StructureTests.user
    tearDown = fixtures.StructureTests.tearDown

    def setUp(self):
        fixtures.StructureTests.setUp(self)
        core.mutate(self.admin, 'person', {**self.req(), 'person': dict(name='Persona demo', role='INF', registration='A01', active=True)})
        self.pid = core.snapshot(self.admin, self.one, '2026-10')['people'][0]['id']
        self.entry()

    def req(self, month='2026-10'):
        with core.connect() as c:
            revision = core.center(c, self.one)['revision']
        return dict(cid=self.one, month=month, revision=revision)

    def entry(self, **extra):
        value = dict(person_id=self.pid, day='2026-10-14', slot='m', code='m', layer='actual')
        value.update(extra)
        return core.mutate(self.admin, 'entry', {**self.req(value['day'][:7]), 'entry': value})

    def enable(self, enabled=True):
        value = self.read()['policy']
        return approvals.configure(core, self.admin, dict(cid=self.one, version=value['version'], enabled=enabled, reason='Processo concordato con HR'))

    def read(self, user=None, month='2026-10'):
        return approvals.read(core, user or self.admin, self.one, month)

    def body(self, action, note='', **extra):
        data = self.read()
        return dict(cid=self.one, month='2026-10', version=data['workflow']['version'], fingerprint=data['fingerprint'], action=action, note=note, **extra)

    def step(self, action, user=None, note='', **extra):
        return approvals.transition(core, user or self.admin, self.body(action, note, **extra))

    def approved(self):
        self.enable(); self.step('submit', self.operator)
        self.step('manager_approve', self.manager, calendar_checked=True)
        return self.step('hr_approve', self.hr)

    def test_default_off_preserves_existing_close_and_reopen(self):
        self.assertFalse(self.read()['policy']['enabled'])
        core.mutate(self.manager, 'period_verify', {**self.req(), 'verified': True})
        core.mutate(self.manager, 'close', self.req())
        with core.connect() as c:
            approvals.require_approved(core, c, self.hr, self.one, '2026-10')
        core.mutate(self.manager, 'reopen', {**self.req(), 'reason': 'Correzione autorizzata'})
        self.assertFalse(self.read()['closed'])
        self.assertEqual(self.read()['workflow']['version'], 0)

    def test_full_workflow_closes_without_hr_presence_write_permission(self):
        self.enable(); submitted = self.step('submit', self.operator)
        self.assertEqual(submitted['workflow']['status'], 'submitted')
        self.assertEqual(self.read(self.operator)['actions'], [])
        verified = self.step('manager_approve', self.manager, calendar_checked=True)
        self.assertTrue(verified['verified']); self.assertEqual(verified['workflow']['status'], 'manager_approved')
        with self.assertRaises(PermissionError):
            core.mutate(self.hr, 'entry', {**self.req(), 'entry': {}})
        final = self.step('hr_approve', self.hr)
        self.assertEqual((final['closed'], final['workflow']['status']), (True, 'hr_approved'))
        self.assertEqual([x['action'] for x in reversed(final['history'])], ['submit', 'manager_approve', 'hr_approve'])
        with core.connect() as c:
            approvals.require_approved(core, c, self.hr, self.one, '2026-10')
        self.assertFalse(final['stale'])

    def test_frozen_presence_and_ordinary_close_cannot_bypass(self):
        self.enable(); self.step('submit', self.operator)
        for action, fields in [('entry', {'entry': {}}), ('delete', {'id': 'missing'}),
                               ('period_verify', {'verified': True}), ('patient', {'patient': {}}),
                               ('person', {'person': {}}), ('apply_rules', {'reason': 'forbidden'}),
                               ('agreement_save', {'person_id': self.pid}), ('center_save', {'config': {}}),
                               ('close', {}), ('reopen', {'reason': 'Correzione autorizzata'})]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                core.mutate(self.admin, action, {**self.req(), **fields})
        # Planning a later period remains possible without mutating reference data.
        self.entry(day='2026-11-14')
        self.assertFalse(self.read()['stale'])
        self.assertTrue(core.snapshot(self.operator, self.one, '2026-10')['approval']['frozen'])

    def test_roles_and_scope_are_enforced_on_server(self):
        self.enable()
        for user in (self.viewer, self.hr):
            with self.assertRaises(PermissionError): self.step('submit', user)
        self.step('submit', self.operator)
        for user in (self.operator, self.viewer, self.hr):
            with self.assertRaises(PermissionError): self.step('manager_approve', user, calendar_checked=True)
        self.step('manager_approve', self.manager, calendar_checked=True)
        with self.assertRaises(PermissionError): self.step('hr_approve', self.manager)
        with self.assertRaises(PermissionError): approvals.read(core, self.manager, self.two, '2026-10')
        with self.assertRaises(PermissionError): approvals.configure(core, self.manager, dict(cid=self.one, version=1, enabled=False, reason='Tentativo disattivazione'))
        with self.assertRaises(PermissionError): approvals.transition(core, self.manager, {**self.body('hr_approve'), 'cid': self.two})

    def test_return_requires_note_unlocks_and_resubmits_with_new_version(self):
        self.enable(); self.step('submit', self.operator)
        with self.assertRaises(ValueError): self.step('return', self.manager, note='no')
        self.step('return', self.manager, note='Correggere gli orari del giorno 14')
        self.assertFalse(core.snapshot(self.operator, self.one, '2026-10')['approval']['frozen'])
        self.entry(day='2026-10-15')
        new = self.step('submit', self.operator)
        self.assertEqual(new['workflow']['version'], 3)
        self.step('manager_approve', self.manager, calendar_checked=True)
        returned = self.step('return', self.hr, note='Verificare il riepilogo delle ore')
        self.assertEqual(returned['workflow']['status'], 'returned')
        self.assertFalse(returned['verified'])

    def test_stale_body_replay_and_concurrent_submissions_only_commit_once(self):
        self.enable(); body = self.body('submit')
        def attempt(_):
            try:
                approvals.transition(core, self.operator, copy.deepcopy(body)); return 'saved'
            except ValueError:
                return 'stale'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, [1, 2])), ['saved', 'stale'])
        self.assertEqual(len(self.read()['history']), 1)
        with self.assertRaises(ValueError): approvals.transition(core, self.operator, body)

    def test_changed_data_requires_return_even_with_fresh_client_fingerprint(self):
        self.enable(); self.step('submit', self.operator)
        # HR profile/workforce updates can change reference data independently.
        with core.connect() as c:
            person = core.objects(c, 'people', self.one)[0]; person['registration'] = 'CORRECTED'
            core.put(c, 'people', self.one, person); c.commit()
        self.assertTrue(self.read()['stale'])
        with self.assertRaises(PermissionError): self.step('manager_approve', self.manager, calendar_checked=True)
        self.step('return', self.manager, note='Riconfermare la matricola aggiornata')
        self.step('submit', self.operator)
        self.step('manager_approve', self.manager, calendar_checked=True)
        self.step('hr_approve', self.hr)
        with core.connect() as c:
            person['role'] = 'OSS'; core.put(c, 'people', self.one, person); c.commit()
        with core.connect() as c, self.assertRaisesRegex(ValueError, 'Dati cambiati'):
            approvals.require_approved(core, c, self.hr, self.one, '2026-10')
        self.assertIn('reopen', self.read(self.hr)['actions'])

    def test_checks_and_calendar_confirmation_are_transactional(self):
        self.enable(); self.step('submit', self.operator)
        with self.assertRaisesRegex(ValueError, 'calendario'):
            self.step('manager_approve', self.manager)
        self.assertFalse(self.read()['verified'])
        self.assertEqual(len(self.read()['history']), 1)
        self.step('return', self.manager, note='Aggiungere un consuntivo mancante')
        self.entry(day='2026-10-15', layer='planned')
        with self.assertRaisesRegex(ValueError, 'consuntivo'):
            self.step('submit', self.operator)
        self.assertEqual(self.read()['workflow']['status'], 'returned')

    def test_empty_month_and_missing_required_times_cannot_be_submitted(self):
        self.enable()
        data = self.read(month='2026-12')
        with self.assertRaisesRegex(ValueError, 'registrazioni effettive'):
            approvals.transition(core, self.operator, dict(cid=self.one, month='2026-12', version=0,
                fingerprint=data['fingerprint'], action='submit', note=''))
        with core.connect() as c:
            ct = core.center(c, self.one); p = core.period(c, ct, '2026-10'); p['config']['require_times_on_close'] = True
            core.put_period(c, self.one, '2026-10', p)
            entry = core.objects(c, 'entries', self.one)[0]; entry['start'] = ''; entry['end'] = ''
            core.put(c, 'entries', self.one, entry); c.commit()
        with self.assertRaisesRegex(ValueError, 'orari'):
            self.step('submit', self.operator)

    def test_revoked_active_role_and_center_are_rechecked(self):
        self.enable(); self.step('submit', self.operator)
        with core.connect() as c:
            c.execute('UPDATE users SET centers=? WHERE id=?', (core.dump([self.two]), self.manager['id'])); c.commit()
        with self.assertRaises(PermissionError): self.step('manager_approve', self.manager, calendar_checked=True)
        with core.connect() as c:
            c.execute('UPDATE users SET active=0 WHERE id=?', (self.operator['id'],)); c.commit()
        with self.assertRaises(core.AuthenticationError): self.read(self.operator)

    def test_legacy_closed_month_stays_readable_without_fabricated_hr_approval(self):
        core.mutate(self.manager, 'period_verify', {**self.req(), 'verified': True})
        core.mutate(self.manager, 'close', self.req()); self.enable()
        data = self.read(self.hr)
        self.assertTrue(data['legacy_closed']); self.assertEqual(data['workflow']['status'], 'draft')
        self.assertEqual(data['history'], [])
        with core.connect() as c:
            approvals.require_approved(core, c, self.hr, self.one, '2026-10')
        self.step('reopen', self.manager, note='Correggere il mese storico chiuso')
        with core.connect() as c, self.assertRaises(ValueError):
            approvals.require_approved(core, c, self.hr, self.one, '2026-10')

    def test_policy_version_and_pending_prevent_disabling_bypass(self):
        self.enable(); self.step('submit', self.operator)
        with self.assertRaisesRegex(ValueError, 'in corso'): self.enable(False)
        with self.assertRaisesRegex(ValueError, 'cambiata'):
            approvals.configure(core, self.admin, dict(cid=self.one, version=0, enabled=False, reason='Configurazione non aggiornata'))
        self.step('return', self.manager, note='Rivedere il processo di verifica'); self.enable(False)
        self.assertFalse(self.read()['policy']['enabled'])

    def test_reopen_invalidates_final_approval_with_or_without_policy(self):
        self.approved()
        self.step('reopen', self.hr, note='Correggere una registrazione finale')
        self.assertFalse(self.read()['closed']); self.assertEqual(self.read()['workflow']['status'], 'returned')
        self.step('submit', self.operator); self.step('manager_approve', self.manager, calendar_checked=True)
        self.step('hr_approve', self.hr); self.enable(False)
        core.mutate(self.manager, 'reopen', {**self.req(), 'reason': 'Processo diverso: correggere mese'})
        self.assertEqual(self.read()['workflow']['status'], 'returned')
        self.assertEqual(self.read()['history'][0]['action'], 'reopen')

    def test_malformed_versions_and_actions_are_rejected(self):
        self.enable()
        for changes in ({'version': True}, {'version': -1}, {'action': []}, {'fingerprint': []}, {'note': 123}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                approvals.transition(core, self.operator, {**self.body('submit'), **changes})


if __name__ == '__main__': unittest.main()
