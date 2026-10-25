import unittest

from test_attendance import MONTH, AttendanceCase


class Workforce(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.hr = self.portal.user('hrcentrale', 'hr')
        self.west = self.portal.center('Centro Ovest', 'OVEST')
        self.portal.step_up(self.admin)
        self.twin = self.admin.ok('POST', f'/api/centers/{self.west}/people', {'name': 'Anna Bianchi', 'role': 'INF'})['id']

    def group_of(self, pid, client=None):
        groups = (client or self.hr).ok('GET', '/api/workforce')['groups']
        return next(g for g in groups if any(a['person_id'] == pid for a in g['assignments']))

    def link(self, client=None, reason='Stessa persona: verificato con il fascicolo'):
        client = client or self.hr
        target = self.group_of(self.anna)
        person = next(a for a in self.group_of(self.twin)['assignments'] if a['person_id'] == self.twin)
        self.portal.step_up(client)
        return client.post(f'/api/workforce/{self.west}/{self.twin}/link',
                           {'identity_id': target['identity_id'], 'identity_version': target['version'],
                            'version': person['version'], 'reason': reason})

    def test_link_is_manual_and_enables_cross_center_checks(self):
        self.assertNotEqual(self.group_of(self.anna)['identity_id'], self.group_of(self.twin)['identity_id'],
                            'nessun collegamento automatico per nome')
        self.assertEqual(self.link().status, 200)
        group = self.group_of(self.anna)
        self.assertTrue(group['linked'])
        self.assertEqual(len(group['assignments']), 2)
        self.admin.ok('POST', f'/api/attendance/{self.west}/{MONTH}/entries',
                      dict(person_id=self.twin, day='2026-10-05', slot='m', code='m', layer='actual'))
        self.assertStatus(self.entry(self.manager), 400, 'Centro Ovest')

    def test_manager_cannot_link_outside_assigned_centers(self):
        self.assertStatus(self.manager.get(f'/api/workforce/{self.group_of(self.twin)["identity_id"]}'), 404)
        target = self.group_of(self.twin, self.hr)
        me = self.group_of(self.anna, self.manager)
        person = me['assignments'][0]
        self.portal.step_up(self.manager)
        response = self.manager.post(f'/api/workforce/{self.cid}/{self.anna}/link',
                                     {'identity_id': target['identity_id'], 'identity_version': target['version'],
                                      'version': person['version'], 'reason': 'Tentativo fuori ambito'})
        self.assertStatus(response, 403)

    def test_contract_intervals_do_not_overlap(self):
        url = f'/api/workforce/{self.cid}/{self.anna}/contracts'
        data = {'role': 'INF', 'contract_type': 'Tempo indeterminato', 'weekly_hours': 36, 'part_time_percent': 100}
        self.portal.step_up(self.hr)
        first = self.hr.ok('PUT', url, {'version': 0, 'valid_from': '2026-01-01', 'data': data, 'reason': 'Assunzione iniziale'})
        clash = self.hr.put(url, {'version': 0, 'valid_from': '2026-10-15', 'data': data, 'reason': 'Passaggio a part-time'})
        self.assertStatus(clash, 400, 'sovrapposti')
        record = first['record']
        self.hr.ok('PUT', url, {'id': record['id'], 'version': record['version'], 'valid_from': '2026-01-01',
                                'valid_to': '2026-10-14', 'data': data, 'reason': 'Chiusura per passaggio a part-time'})
        part = dict(data, part_time_percent=50, weekly_hours=18)
        self.hr.ok('PUT', url, {'version': 0, 'valid_from': '2026-10-15', 'data': part, 'reason': 'Passaggio a part-time'})
        detail = self.hr.ok('GET', f'/api/workforce/{self.group_of(self.anna)["identity_id"]}?on=2026-10-20')
        self.assertEqual(detail['assignments'][0]['contract']['part_time_percent'], 50)
        self.assertEqual(len(detail['assignments'][0]['contracts']), 2)

    def economic(self, start, end, **changes):
        base = self.hr.ok('GET', f'/api/agreements/{self.cid}/{MONTH}')['rows'][0]['agreement']
        data = {**base, 'basis': 'all', 'confirmed': True, 'fixed_deduction': 0, **changes}
        self.portal.step_up(self.hr)
        return self.hr.put(f'/api/workforce/{self.cid}/{self.anna}/economics',
                           {'version': 0, 'valid_from': start, 'valid_to': end, 'data': data, 'reason': 'Condizioni concordate'})

    def test_mid_month_change_is_split_and_applied(self):
        self.entry(self.manager, day='2026-10-05')
        self.entry(self.manager, day='2026-10-20')
        self.assertEqual(self.economic('2026-10-01', '2026-10-15', weekday_rate=50).status, 200)
        self.assertEqual(self.economic('2026-10-16', '', weekday_rate=60).status, 200)
        preview = self.hr.ok('GET', f'/api/workforce/{self.cid}/{self.anna}/preview/{MONTH}')
        self.assertFalse(preview['manual_required'], preview['message'])
        self.assertEqual(preview['result']['amount'], 50 + 60)
        self.portal.step_up(self.hr)
        applied = self.hr.ok('POST', f'/api/workforce/{self.cid}/{self.anna}/apply',
                             {'month': MONTH, 'reason': 'Applicazione decorrenze di ottobre', 'agreement_version': 0})
        self.assertEqual(applied['version'], 1)
        row = next(r for r in self.manager.ok('GET', f'/api/agreements/{self.cid}/{MONTH}')['rows'] if r['person_id'] == self.anna)
        self.assertEqual(row['amount'], 110)
        self.assertEqual(len(row['segments']), 2)

    def test_mid_month_change_with_deduction_requires_manual_agreement(self):
        self.assertEqual(self.economic('2026-10-01', '2026-10-15', fixed_deduction=100).status, 200)
        self.assertEqual(self.economic('2026-10-16', '').status, 200)
        preview = self.hr.ok('GET', f'/api/workforce/{self.cid}/{self.anna}/preview/{MONTH}')
        self.assertTrue(preview['manual_required'])
        self.portal.step_up(self.hr)
        refused = self.hr.post(f'/api/workforce/{self.cid}/{self.anna}/apply',
                               {'month': MONTH, 'reason': 'Applicazione decorrenze', 'agreement_version': 0})
        self.assertStatus(refused, 400, 'manuale')

    def test_gap_in_month_is_reported(self):
        self.assertEqual(self.economic('2026-10-10', '').status, 200)
        preview = self.hr.ok('GET', f'/api/workforce/{self.cid}/{self.anna}/preview/{MONTH}')
        self.assertIn('ogni giorno del mese', preview['message'])


if __name__ == '__main__':
    unittest.main()
