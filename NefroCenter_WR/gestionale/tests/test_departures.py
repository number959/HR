import unittest

from test_attendance import AttendanceCase


class Departures(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.hr = self.portal.user('hrcentrale', 'hr')

    def open_case(self, **extra):
        body = {'person_id': self.anna, 'kind': 'termination', 'reason': 'Dimissioni volontarie', 'effective_date': '2026-11-30',
                'responsible': 'Ufficio HR', 'version': 0, **extra}
        return self.hr.post(f'/api/departures/{self.cid}', body)

    def asset(self, code='BADGE-001'):
        return self.hr.ok('POST', f'/api/equipment/{self.cid}', {'person_id': self.anna, 'kind': 'badge', 'inventory_code': code,
                                                               'label': 'Badge di accesso', 'delivery_date': '2026-01-10',
                                                               'version': 0})['asset']

    def test_case_closes_only_after_tasks_and_returns(self):
        case = self.open_case()
        self.assertEqual(case.status, 200, case.body)
        case = case.data
        self.assertStatus(self.open_case(), 400, 'già un percorso aperto')
        asset = self.asset()
        url = f'/api/departures/{self.cid}/{case["id"]}'
        refused = self.hr.post(url + '/close', {'status': 'completed', 'note': 'Chiusura del percorso', 'confirm': True,
                                                'version': case['version']})
        self.assertStatus(refused, 400, 'Completare')
        version = case['version']
        for task in case['tasks']:
            version = self.hr.ok('PUT', f'{url}/tasks/{task["id"]}', {'status': 'done', 'version': version})['version']
        self.hr.ok('POST', f'/api/equipment/{self.cid}/{asset["id"]}/return',
                   {'return_date': '2026-10-20', 'condition': 'good', 'version': asset['version']})
        closed = self.hr.ok('POST', url + '/close', {'status': 'completed', 'note': 'Chiusura del percorso', 'confirm': True,
                                                     'version': version})
        self.assertEqual(closed['status'], 'completed')
        self.assertIn('non cambia automaticamente', closed['notice'])

    def test_asset_rules(self):
        asset = self.asset()
        self.assertStatus(self.hr.post(f'/api/equipment/{self.cid}', {'person_id': self.luca, 'kind': 'badge',
                                                                        'inventory_code': ' badge-001 ', 'label': 'Altro',
                                                                        'delivery_date': '2026-01-10', 'version': 0}), 400, 'già assegnata')
        rewrite = self.hr.put(f'/api/equipment/{self.cid}/{asset["id"]}', {'person_id': self.luca, 'kind': 'badge',
                                                                            'inventory_code': 'BADGE-001', 'label': 'Badge',
                                                                            'delivery_date': '2026-01-10',
                                                                            'version': asset['version']})
        self.assertStatus(rewrite, 400, 'non si riscrivono')
        damaged = self.hr.post(f'/api/equipment/{self.cid}/{asset["id"]}/return',
                               {'return_date': '2026-10-20', 'condition': 'damaged', 'version': asset['version']})
        self.assertStatus(damaged, 400, 'danni')

    def test_transfer_requires_other_center_and_operator_is_excluded(self):
        self.assertStatus(self.open_case(kind='transfer'), 400, 'destinazione')
        self.assertStatus(self.operator.get('/api/departures'), 403)
        overview = self.hr.ok('GET', '/api/departures')
        self.assertIn('Centro Dialisi Est', [c['name'] for c in overview['centers']])


if __name__ == '__main__':
    unittest.main()
