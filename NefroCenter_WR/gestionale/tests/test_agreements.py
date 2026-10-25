import unittest

from test_attendance import MONTH, AttendanceCase


class Agreements(AttendanceCase):
    def report(self, client=None):
        return (client or self.manager).ok('GET', f'/api/agreements/{self.cid}/{MONTH}')

    def row(self, report, pid):
        return next(r for r in report['rows'] if r['person_id'] == pid)

    def save(self, pid, agreement, version=0, reason='Accordo firmato il 1 ottobre', client=None):
        client = client or self.manager
        self.portal.step_up(client)
        return client.put(f'/api/agreements/{self.cid}/{MONTH}/{pid}',
                          {'agreement': agreement, 'reason': reason, 'version': version})

    def test_proposal_has_no_amount_until_confirmed(self):
        row = self.row(self.report(), self.anna)
        self.assertEqual(row['status'], 'da_confermare')
        self.assertIsNone(row['amount'])
        self.assertFalse(row['saved'])
        self.assertEqual(row['agreement']['weekday_rate'], 50)

    def test_confirmed_turns_agreement(self):
        for day in ('2026-10-05', '2026-10-06'):
            self.entry(self.manager, day=day)
        self.entry(self.manager, day='2026-10-07', holiday=True)
        agreement = dict(self.row(self.report(), self.anna)['agreement'], basis='all', confirmed=True)
        saved = self.save(self.anna, agreement)
        self.assertEqual(saved.status, 200, saved.body)
        row = self.row(self.report(), self.anna)
        self.assertEqual((row['units'], row['festive_units'], row['ordinary_units']), (3, 1, 2))
        self.assertEqual(row['amount'], 2 * 50 + 1 * 70 - 100)
        self.assertEqual(row['status'], 'calcolato')
        self.assertTrue(row['saved'])
        self.assertStatus(self.save(self.anna, agreement, version=0), 409)
        self.assertFalse(self.snap()['state']['verified'], 'un accordo salvato richiede una nuova verifica del mese')

    def test_permissions_and_reason(self):
        agreement = dict(self.row(self.report(), self.anna)['agreement'], confirmed=True)
        hr = self.portal.user('hrcentrale', 'hr')
        self.assertEqual(self.report(hr)['center']['id'], self.cid)
        self.assertStatus(self.save(self.anna, agreement, client=hr), 403)
        self.assertStatus(self.operator.get(f'/api/agreements/{self.cid}/{MONTH}'), 403)
        self.assertStatus(self.save(self.anna, agreement, reason='corto'), 400)

    def test_hours_model_needs_times(self):
        self.entry(self.manager, start='', end='')
        agreement = dict(self.row(self.report(), self.anna)['agreement'], model='hours', confirmed=True)
        self.assertEqual(self.save(self.anna, agreement).status, 200)
        self.assertEqual(self.row(self.report(), self.anna)['status'], 'orari_mancanti')

    def test_excel_model_simulation(self):
        result = self.manager.ok('POST', f'/api/agreements/{self.cid}/{MONTH}/simulate', {'total': 30, 'festive': 2})
        self.assertEqual(result['theoretical'], 27)
        self.assertEqual((result['extra'], result['ordinary'], result['total']), (3, 1, 1 * 50 + 2 * 70 - 100))
        empty = self.manager.ok('POST', f'/api/agreements/{self.cid}/{MONTH}/simulate', {'total': 0, 'festive': 0})
        self.assertFalse(empty['calculated'])
        self.assertStatus(self.manager.post(f'/api/agreements/{self.cid}/{MONTH}/simulate', {'total': 1.5, 'festive': 0}), 400)


if __name__ == '__main__':
    unittest.main()
