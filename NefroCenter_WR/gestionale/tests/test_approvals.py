import unittest

from test_attendance import MONTH, AttendanceCase


class MonthlyApproval(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.hr = self.portal.user('hrcentrale', 'hr')
        self.url = f'/api/approvals/{self.cid}/{MONTH}'

    def enable(self, enabled=True):
        policy = self.admin.ok('GET', self.url)['policy']
        self.portal.step_up(self.admin)
        return self.admin.put(f'/api/approvals/{self.cid}/policy',
                              {'enabled': enabled, 'reason': 'Percorso concordato con HR', 'version': policy['version']})

    def act(self, client, action, **extra):
        state = client.ok('GET', self.url)
        return client.post(self.url, {'action': action, 'version': state['workflow']['version'],
                                      'fingerprint': state['fingerprint'], **extra})

    def test_only_admin_configures(self):
        self.assertStatus(self.manager.put(f'/api/approvals/{self.cid}/policy',
                                           {'enabled': True, 'reason': 'Tentativo non ammesso', 'version': 0}), 403)
        self.assertFalse(self.manager.ok('GET', self.url)['policy']['enabled'])
        self.assertEqual(self.enable().status, 200)

    def test_full_path_freezes_and_closes(self):
        self.enable()
        self.entry(self.operator)
        self.assertEqual([a['id'] for a in self.operator.ok('GET', self.url)['actions']], ['submit'])
        self.assertEqual(self.act(self.operator, 'submit').status, 200)
        self.assertStatus(self.entry(self.operator, day='2026-10-06'), 400, 'inviato o approvato')
        self.assertTrue(self.snap(self.operator)['approval']['frozen'])
        self.assertStatus(self.act(self.hr, 'hr_approve'), 403)
        self.assertStatus(self.act(self.manager, 'manager_approve'), 400, 'calendario')
        self.assertEqual(self.act(self.manager, 'manager_approve', calendar_checked=True).status, 200)
        approved = self.act(self.hr, 'hr_approve')
        self.assertEqual(approved.status, 200, approved.body)
        self.assertTrue(approved.data['closed'])
        self.assertEqual(approved.data['workflow']['status'], 'hr_approved')
        self.assertStatus(self.entry(self.manager, day='2026-10-07'), 400)
        # La chiusura diretta non è disponibile con il percorso attivo.
        state = self.snap()['state']
        self.assertStatus(self.manager.post(f'/api/attendance/{self.cid}/{MONTH}/reopen',
                                            {'version': state['version'], 'reason': 'Riapertura diretta'}), 400, 'Approvazioni')
        reopened = self.act(self.manager, 'reopen', note='Correzione richiesta dal consulente')
        self.assertEqual(reopened.status, 200)
        self.assertFalse(reopened.data['closed'])
        self.assertEqual(self.entry(self.operator, day='2026-10-07').status, 200)

    def test_return_requires_reason_and_unfreezes(self):
        self.enable()
        self.entry(self.operator)
        self.act(self.operator, 'submit')
        self.assertStatus(self.act(self.manager, 'return', note='no'), 400)
        self.assertEqual(self.act(self.manager, 'return', note='Manca il turno del 6 ottobre').status, 200)
        self.assertEqual(self.entry(self.operator, day='2026-10-06').status, 200)
        history = self.manager.ok('GET', self.url)['history']
        self.assertEqual([h['action'] for h in history], ['return', 'submit'])

    def test_stale_fingerprint_is_rejected(self):
        self.enable()
        self.entry(self.operator)
        state = self.operator.ok('GET', self.url)
        self.entry(self.operator, day='2026-10-06')
        response = self.operator.post(self.url, {'action': 'submit', 'version': state['workflow']['version'],
                                                 'fingerprint': state['fingerprint']})
        self.assertStatus(response, 409)

    def test_reference_data_locked_while_in_progress(self):
        self.enable()
        self.entry(self.operator)
        self.act(self.operator, 'submit')
        response = self.manager.put(f'/api/centers/{self.cid}/people/{self.anna}', {'name': 'Anna B.', 'version': 1})
        self.assertStatus(response, 400, 'dati di riferimento')
        self.assertStatus(self.enable(False), 400, 'approvazione in corso')

    def test_queue_shows_what_waits_for_me(self):
        self.enable()
        self.entry(self.operator)
        self.act(self.operator, 'submit')
        self.act(self.manager, 'manager_approve', calendar_checked=True)
        queue = self.hr.ok('GET', f'/api/approvals/{MONTH}')
        row = next(r for r in queue['centers'] if r['center_id'] == self.cid)
        self.assertTrue(row['mine'])
        self.assertEqual(queue['waiting'], 1)

    def test_disabled_policy_reopen_invalidates_previous_approval(self):
        self.enable()
        self.entry(self.operator)
        self.act(self.operator, 'submit')
        self.act(self.manager, 'manager_approve', calendar_checked=True)
        self.act(self.hr, 'hr_approve')
        self.assertEqual(self.enable(False).status, 200)
        state = self.snap()['state']
        self.manager.ok('POST', f'/api/attendance/{self.cid}/{MONTH}/reopen',
                        {'version': state['version'], 'reason': 'Correzione dopo disattivazione'})
        self.assertEqual(self.manager.ok('GET', self.url)['workflow']['status'], 'returned')


if __name__ == '__main__':
    unittest.main()
