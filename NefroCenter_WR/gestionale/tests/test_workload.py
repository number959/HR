"""Indicatori del carico (rapporti, efficienza, sintesi del mese) e conteggi del mese per persona e gruppo.

Dati fittizi; i valori attesi sono calcolati a mano con i parametri predefiniti della struttura:
5 pazienti per infermiere, 20 per medico, peso 5 per un paziente in isolamento, soglia 0,92.
"""
import unittest

from test_attendance import AttendanceCase, MONTH


class WorkloadIndicators(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.bea = self.person('Beatrice Neri', 'INF', 'M003')
        self.carla = self.person('Carla Rossi', 'INF', 'M004')
        self.assertEqual(self.save_config(lambda c: c.update(sites=['Altra sede'])).status, 200)
        cfg = self.config()['config']
        self.assertEqual((cfg['nurse_reference'], cfg['doctor_reference'], cfg['isolation_weight'], cfg['efficiency_threshold']),
                         (5, 20, 5, 0.92))

    def fill(self):
        # 5/10 mattina: due infermieri e un medico nella sede, un terzo infermiere fuori sede (escluso dal conteggio).
        for person in (self.anna, self.bea, self.luca):
            self.assertEqual(self.entry(self.manager, day='2026-10-05', person=person).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-05', person=self.carla, site='Altra sede').status, 200)
        # 6/10 mattina: una sola infermiera; 6/10 pomeriggio: la stessa (riposo zero → solo avviso).
        self.assertEqual(self.entry(self.manager, day='2026-10-06', person=self.anna).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-06', slot='p', code='p', person=self.anna).status, 200)
        # 7/10 mattina festivo: turno senza pazienti registrati (conta nei turni, non nei giorni con dati).
        self.assertEqual(self.entry(self.manager, day='2026-10-07', person=self.anna, holiday=True).status, 200)
        # Assenza: ferie di Beatrice il 5/10 pomeriggio.
        self.assertEqual(self.entry(self.manager, day='2026-10-05', slot='p', code='FE', person=self.bea).status, 200)
        url = f'/api/attendance/{self.cid}/{MONTH}/workload'
        self.manager.ok('PUT', url, {'day': '2026-10-05', 'slot': 'm', 'ordinary': 9, 'isolated': 1})
        self.manager.ok('PUT', url, {'day': '2026-10-06', 'slot': 'm', 'ordinary': 4, 'isolated': 0})
        self.manager.ok('PUT', url, {'day': '2026-10-06', 'slot': 'p', 'ordinary': 5, 'isolated': 0})

    def test_daily_rows_have_efficiency_and_level(self):
        self.fill()
        rows = self.snap()['workload']
        self.assertEqual([(r['day'], r['slot']) for r in rows], [('2026-10-05', 'm'), ('2026-10-06', 'm'), ('2026-10-06', 'p')])
        first = rows[0]
        self.assertEqual((first['nurses'], first['doctors']), (2, 1), 'l’infermiera fuori sede non conta')
        self.assertAlmostEqual(first['nurse_ratio'], 7.0)
        self.assertAlmostEqual(first['nurse_efficiency'], 1.4)
        self.assertEqual(first['nurse_level'], 'oltre')
        self.assertAlmostEqual(first['doctor_ratio'], 10.0)
        self.assertAlmostEqual(first['doctor_efficiency'], 0.5)
        self.assertEqual(first['doctor_level'], 'sotto')
        second = rows[1]
        self.assertEqual(second['nurses'], 1)
        self.assertAlmostEqual(second['nurse_efficiency'], 0.8)
        self.assertEqual(second['nurse_level'], 'sotto')
        self.assertIsNone(second['doctor_ratio'])
        self.assertIsNone(second['doctor_efficiency'])
        self.assertEqual(second['doctor_level'], 'nessuno')
        self.assertTrue(second['uncovered'])
        afternoon = rows[2]
        self.assertAlmostEqual(afternoon['nurse_efficiency'], 1.0)
        self.assertEqual(afternoon['nurse_level'], 'adeguato')

    def test_month_summary_by_slot_and_totals(self):
        self.fill()
        summary = self.snap()['workload_summary']
        by_slot = {s['slot']: s for s in summary['slots']}
        self.assertEqual(list(by_slot), ['m', 'p', 's', 'n'], 'una riga per ogni fascia attiva')
        m = by_slot['m']
        # Turni mattina nella sede: Anna 5, 6 e 7 + Beatrice 5 = 4 (Carla fuori sede esclusa); medici: Luca il 5.
        self.assertEqual((m['days'], m['nurse_shifts'], m['doctor_shifts']), (2, 4, 1))
        self.assertEqual((m['ordinary'], m['isolated'], m['patients']), (13, 1, 14))
        self.assertAlmostEqual(m['nurse_ratio'], (13 + 1 * 5) / 4)
        self.assertAlmostEqual(m['nurse_efficiency'], 0.9)
        self.assertEqual(m['nurse_level'], 'sotto')
        self.assertAlmostEqual(m['doctor_ratio'], 14.0)
        self.assertAlmostEqual(m['doctor_efficiency'], 0.7)
        self.assertEqual(m['doctor_level'], 'sotto')
        p = by_slot['p']
        self.assertEqual((p['days'], p['nurse_shifts'], p['doctor_shifts'], p['patients']), (1, 1, 0, 5))
        self.assertAlmostEqual(p['nurse_ratio'], 5.0)
        self.assertEqual(p['nurse_level'], 'adeguato')
        self.assertIsNone(p['doctor_ratio'])
        self.assertEqual(p['doctor_level'], 'nessuno')
        s = by_slot['s']
        self.assertEqual((s['days'], s['nurse_shifts'], s['patients']), (0, 0, 0))
        self.assertIsNone(s['nurse_ratio'])
        self.assertEqual(s['nurse_level'], 'nessuno')
        # Complessivi: «Totale turni da lavorare» e «Totale dialisi da effettuare».
        self.assertEqual((summary['nurse_shifts'], summary['doctor_shifts']), (5, 1))
        self.assertEqual((summary['ordinary'], summary['isolated'], summary['patients'], summary['days']), (18, 1, 19, 2))
        # «Media parametro»: media dei rapporti delle fasce con dati (mattina 4,5 e pomeriggio 5,0).
        self.assertAlmostEqual(summary['nurse_parameter'], 4.75)
        self.assertAlmostEqual(summary['nurse_efficiency'], 0.95)
        self.assertEqual(summary['nurse_level'], 'adeguato')
        self.assertAlmostEqual(summary['doctor_parameter'], 14.0)
        self.assertAlmostEqual(summary['doctor_efficiency'], 0.7)
        self.assertEqual(summary['doctor_level'], 'sotto')
        self.assertEqual((summary['threshold'], summary['nurse_reference'], summary['doctor_reference'],
                          summary['isolation_weight']), (0.92, 5, 20, 5))
        self.assertEqual((summary['dialysis_stations'], summary['isolation_stations']), (0, 0))

    def test_summary_without_patients_has_no_ratio_but_counts_shifts(self):
        self.assertEqual(self.entry(self.manager, day='2026-10-05', person=self.anna).status, 200)
        summary = self.snap()['workload_summary']
        m = next(s for s in summary['slots'] if s['slot'] == 'm')
        self.assertEqual((m['days'], m['nurse_shifts'], m['patients']), (0, 1, 0))
        self.assertIsNone(m['nurse_ratio'])
        self.assertEqual(m['nurse_level'], 'nessuno')
        self.assertIsNone(summary['nurse_parameter'])
        self.assertEqual(summary['nurse_shifts'], 1)

    def test_stations_follow_the_month_parameters(self):
        self.assertEqual(self.save_config(lambda c: c.update(dialysis_stations=24, isolation_stations=2)).status, 200)
        summary = self.snap()['workload_summary']
        self.assertEqual((summary['dialysis_stations'], summary['isolation_stations']), (24, 2))


class MonthCounters(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.bea = self.person('Beatrice Neri', 'INF', 'M003')
        self.carla = self.person('Carla Rossi', 'INF', 'M004')
        self.assertEqual(self.save_config(lambda c: c.update(sites=['Altra sede'])).status, 200)

    def fill(self):
        WorkloadIndicators.fill(self)

    def test_people_rows_and_group_totals(self):
        self.fill()
        # Persona non attiva senza registrazioni: resta fuori dai conteggi.
        dormant = self.person('Dina Gallo', 'OSS', 'M005')
        self.manager.ok('PUT', f'/api/centers/{self.cid}/people/{dormant}', {'active': False, 'version': 1})
        counters = self.snap()['counters']
        code_ids = [c['id'] for c in counters['codes']]
        self.assertEqual(code_ids[:3], ['FE', 'PS', 'ROL'])
        self.assertIn('R', code_ids)
        self.assertNotIn('m', code_ids, 'i codici di lavoro non diventano colonne')
        self.assertEqual(next(c for c in counters['codes'] if c['id'] == 'FE')['label'], 'Ferie')
        by_name = {r['name']: r for r in counters['people']}
        self.assertEqual(set(by_name), {'Anna Bianchi', 'Beatrice Neri', 'Carla Rossi', 'Luca Verdi'})
        anna = by_name['Anna Bianchi']
        self.assertEqual((anna['shifts'], anna['external'], anna['festive'], anna['absences'], anna['total']), (4, 0, 1, 0, 4))
        self.assertEqual(anna['codes']['FE'], 0)
        self.assertEqual(anna['group'], 'infermieri')
        bea = by_name['Beatrice Neri']
        self.assertEqual((bea['shifts'], bea['absences'], bea['codes']['FE'], bea['total']), (1, 1, 1, 2))
        carla = by_name['Carla Rossi']
        self.assertEqual((carla['shifts'], carla['external'], carla['total']), (1, 1, 1))
        luca = by_name['Luca Verdi']
        self.assertEqual((luca['shifts'], luca['group'], luca['total']), (1, 'medici', 1))
        groups = {g['id']: g for g in counters['groups']}
        self.assertEqual(list(groups), ['infermieri', 'medici', 'tutti'], 'i gruppi vuoti non compaiono; il totale sempre')
        nurses = groups['infermieri']
        self.assertEqual((nurses['people'], nurses['shifts'], nurses['external'], nurses['festive'], nurses['codes']['FE'],
                          nurses['total']), (3, 6, 1, 1, 1, 7))
        self.assertEqual((groups['medici']['people'], groups['medici']['shifts']), (1, 1))
        everyone = groups['tutti']
        self.assertEqual(everyone['label'], 'Tutto il personale')
        self.assertEqual((everyone['people'], everyone['shifts'], everyone['external'], everyone['codes']['FE'], everyone['total']),
                         (4, 7, 1, 1, 8))

    def test_inactive_person_with_entries_stays_and_planned_is_not_counted(self):
        self.assertEqual(self.entry(self.manager, day='2026-10-05', person=self.bea).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-06', person=self.bea, layer='planned').status, 200)
        self.manager.ok('PUT', f'/api/centers/{self.cid}/people/{self.bea}', {'active': False, 'version': 1})
        counters = self.snap()['counters']
        bea = next(r for r in counters['people'] if r['person_id'] == self.bea)
        self.assertFalse(bea['active'])
        self.assertEqual((bea['shifts'], bea['total']), (1, 1), 'le fasce solo pianificate non sono registrazioni')
        groups = {g['id']: g for g in counters['groups']}
        self.assertEqual(groups['tutti']['people'], 4, 'Anna, Beatrice, Carla e Luca')

    def test_operator_gets_counters_but_not_workload_summary(self):
        self.fill()
        snap = self.snap(self.operator)
        self.assertFalse(snap['caps']['presenze.carico'])
        self.assertIsNone(snap['workload_summary'])
        self.assertEqual(snap['workload'], [])
        self.assertEqual(len(snap['counters']['people']), 4)
        self.assertEqual(snap['counters']['groups'][-1]['shifts'], 7)
        manager = self.snap()
        self.assertIsNotNone(manager['workload_summary'])
        self.assertEqual(manager['counters'], snap['counters'])


if __name__ == '__main__':
    unittest.main()
