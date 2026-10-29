import unittest

from test_attendance import MONTH, AttendanceCase


class Collaborators(AttendanceCase):
    """Prospetto dei collaboratori a prestazione (il foglio «Collaboratori» del vecchio modello Excel)."""

    def setUp(self):
        super().setUp()
        self.hr = self.portal.user('hrcentrale', 'hr')
        # Anna diventa collaboratrice con fattura: tipo di rapporto, ritenuta 20 %, cassa ENPAPI 4 %, IBAN fittizio valido.
        detail = self.hr.ok('GET', f'/api/hr/{self.cid}/{self.anna}')
        fields = dict(detail['profile']['fields'], relationship='professionista', billing_entity='Studio di prova',
                      withholding_rate='20', fund_name='ENPAPI', fund_rate='4', iban='IT60X0542811101000000123456',
                      account_holder='Anna Bianchi')
        self.hr.ok('PUT', f'/api/hr/{self.cid}/{self.anna}', {'name': 'Anna Bianchi', 'role': 'INF', 'registration': 'M001',
                                                              'stage': 'active', 'fields': fields, 'custom': {},
                                                              'version': detail['profile']['version']})

    def statement(self, client=None):
        return (client or self.hr).ok('GET', f'/api/collaborators/{self.cid}/{MONTH}')

    def test_employees_stay_out_and_relationship_is_a_closed_choice(self):
        data = self.statement()
        self.assertEqual([r['name'] for g in data['groups'] for r in g['rows']], ['Anna Bianchi'])
        self.assertEqual(data['groups'][0]['label'], 'Collaboratore con fattura (libero professionista)')
        detail = self.hr.ok('GET', f'/api/hr/{self.cid}/{self.luca}')
        bad = self.hr.put(f'/api/hr/{self.cid}/{self.luca}', {'name': 'Luca Verdi', 'role': 'MED', 'registration': 'M002', 'stage': 'active',
                                                               'fields': dict(detail['profile']['fields'], relationship='inventato'),
                                                               'custom': {}, 'version': detail['profile']['version']})
        self.assertStatus(bad, 400, 'Tipo di rapporto')

    def test_amounts_follow_the_confirmed_agreement(self):
        for day in ('2026-10-05', '2026-10-06', '2026-10-07'):
            self.entry(self.manager, day=day)
        self.entry(self.manager, day='2026-10-11', holiday=True)
        row = self.statement()['groups'][0]['rows'][0]
        self.assertEqual((row['shifts'], row['gross'], row['net'], row['status']), (4, None, None, 'da_confermare'))
        report = self.manager.ok('GET', f'/api/agreements/{self.cid}/{MONTH}')
        agreement = next(r for r in report['rows'] if r['person_id'] == self.anna)['agreement']
        agreement.update(basis='all', weekday_rate=62.5, holiday_rate=87.5, fixed_deduction=0, confirmed=True)
        self.portal.step_up(self.manager)
        self.manager.ok('PUT', f'/api/agreements/{self.cid}/{MONTH}/{self.anna}', {'agreement': agreement, 'reason': 'Tariffe concordate', 'version': 0})
        data = self.statement()
        row = data['groups'][0]['rows'][0]
        self.assertEqual((row['ordinary_units'], row['festive_units']), (3, 1))
        self.assertEqual(row['gross'], 3 * 62.5 + 87.5)            # 275.00
        self.assertEqual(row['withholding'], 55.0)                  # 20 %
        self.assertEqual(row['fund'], 11.0)                         # 4 %
        self.assertEqual(row['net'], 275 + 11 - 55)
        self.assertEqual(row['iban'], 'IT60X0542811101000000123456')
        self.assertEqual(data['totals']['net'], 231.0)
        # Il responsabile della struttura (area HR) vede il prospetto completo; compilatore e direzione non vi accedono.
        mine = self.statement(self.manager)
        self.assertTrue(mine['bank_visible'])
        self.assertStatus(self.operator.get(f'/api/collaborators/{self.cid}/{MONTH}'), 403)
        viewer = self.portal.user('direzione', 'viewer', [self.cid])
        self.assertStatus(viewer.get(f'/api/collaborators/{self.cid}/{MONTH}'), 403)
        self.assertStatus(self.operator.get(f'/api/collaborators/{self.cid}/{MONTH}/export.xlsx'), 403)
        self.portal.step_up(self.hr)
        xlsx = self.hr.request('GET', f'/api/collaborators/{self.cid}/{MONTH}/export.xlsx')
        self.assertEqual(xlsx.status, 200, xlsx.body[:200])
        self.assertIn('collaboratori_EST_2026-10.xlsx', xlsx.header('Content-Disposition'))
        self.assertTrue(xlsx.body.startswith(b'PK'))

    def test_theoretical_adjustment_models_the_excel_franchise(self):
        for day in ('2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08'):
            self.entry(self.manager, day=day, person=self.luca)
        report = self.manager.ok('GET', f'/api/agreements/{self.cid}/{MONTH}')
        row = next(r for r in report['rows'] if r['person_id'] == self.luca)
        agreement = dict(row['agreement'], theoretical_mode='manual', theoretical_units=2, confirmed=True)
        self.portal.step_up(self.manager)
        self.manager.ok('PUT', f'/api/agreements/{self.cid}/{MONTH}/{self.luca}', {'agreement': agreement, 'reason': 'Prova franchigia', 'version': 0})
        base = next(r for r in self.manager.ok('GET', f'/api/agreements/{self.cid}/{MONTH}')['rows'] if r['person_id'] == self.luca)
        self.assertEqual(base['base_units'], 2)
        agreement = dict(base['agreement'], theoretical_mode='calendar', theoretical_adjustment=-(base['calendar_days'] - 2) + 2)
        self.portal.step_up(self.manager)
        self.manager.ok('PUT', f'/api/agreements/{self.cid}/{MONTH}/{self.luca}', {'agreement': agreement, 'reason': 'Correzione teorico', 'version': 1})
        adjusted = next(r for r in self.manager.ok('GET', f'/api/agreements/{self.cid}/{MONTH}')['rows'] if r['person_id'] == self.luca)
        self.assertEqual(adjusted['theoretical'], 4)   # giorni del calendario ridotti fino a 4
        self.assertEqual(adjusted['base_units'], 0)
        # Un accordo salvato prima dell'aggiunta del campo resta valido (il campo manca: vale 0).
        old = {k: val for k, val in adjusted['agreement'].items() if k != 'theoretical_adjustment'}
        self.portal.step_up(self.manager)
        saved = self.manager.put(f'/api/agreements/{self.cid}/{MONTH}/{self.luca}', {'agreement': old, 'reason': 'Senza correzione', 'version': 2})
        self.assertEqual(saved.status, 200, saved.body)


if __name__ == '__main__':
    unittest.main()
