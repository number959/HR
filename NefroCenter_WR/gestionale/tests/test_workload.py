"""Indicatori del carico (rapporti, efficienza, sintesi del mese) e conteggi del mese per persona e gruppo.

Dati fittizi; i valori attesi sono calcolati a mano con i parametri predefiniti della struttura:
5 pazienti per infermiere, 20 per medico, peso 5 per un paziente in isolamento, soglia 0,92.
Come nel vecchio modello: il rapporto mensile di una fascia usa gli stessi giorni al numeratore e al
denominatore; l'efficienza ha due letture (adeguata da soglia in su, sotto soglia sotto); il totale dei
conteggi non comprende i recuperi turno (RC) né i riposi.
"""
import unittest

from test_attendance import AttendanceCase, MONTH

from wr.attendance import efficiency_level, summary_level


class WorkloadIndicators(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.bea = self.person('Beatrice Neri', 'INF', 'M003')
        self.carla = self.person('Carla Rossi', 'INF', 'M004')
        self.assertEqual(self.save_config(lambda c: c.update(sites=['Altra sede'])).status, 200)
        cfg = self.config()['config']
        self.assertEqual((cfg['nurse_reference'], cfg['doctor_reference'], cfg['isolation_weight'], cfg['efficiency_threshold']),
                         (5, 20, 5, 0.92))
        self.workload_url = f'/api/attendance/{self.cid}/{MONTH}/workload'

    def patients(self, day, slot, ordinary, isolated=0):
        self.manager.ok('PUT', self.workload_url, {'day': day, 'slot': slot, 'ordinary': ordinary, 'isolated': isolated})

    def fill(self):
        # 5/10 mattina: due infermieri e un medico nella sede, un terzo infermiere fuori sede (escluso dal conteggio).
        for person in (self.anna, self.bea, self.luca):
            self.assertEqual(self.entry(self.manager, day='2026-10-05', person=person).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-05', person=self.carla, site='Altra sede').status, 200)
        # 6/10 mattina: una sola infermiera; 6/10 pomeriggio: la stessa (riposo zero → solo avviso).
        self.assertEqual(self.entry(self.manager, day='2026-10-06', person=self.anna).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-06', slot='p', code='p', person=self.anna).status, 200)
        # 7/10 mattina festivo: turno senza pazienti registrati (conta nei turni da lavorare, non nel rapporto).
        self.assertEqual(self.entry(self.manager, day='2026-10-07', person=self.anna, holiday=True).status, 200)
        # Assenza: ferie di Beatrice il 5/10 pomeriggio.
        self.assertEqual(self.entry(self.manager, day='2026-10-05', slot='p', code='FE', person=self.bea).status, 200)
        self.patients('2026-10-05', 'm', 9, 1)
        self.patients('2026-10-06', 'm', 4)
        self.patients('2026-10-06', 'p', 5)

    def slot(self, summary, slot_id):
        return next(s for s in summary['slots'] if s['slot'] == slot_id)

    def test_daily_rows_have_efficiency_and_level(self):
        self.fill()
        rows = self.snap()['workload']
        self.assertEqual([(r['day'], r['slot']) for r in rows], [('2026-10-05', 'm'), ('2026-10-06', 'm'), ('2026-10-06', 'p')])
        first = rows[0]
        self.assertEqual((first['nurses'], first['doctors']), (2, 1), 'l’infermiera fuori sede non conta')
        self.assertAlmostEqual(first['nurse_ratio'], 7.0)
        self.assertAlmostEqual(first['nurse_efficiency'], 1.4)
        self.assertEqual(first['nurse_level'], 'adeguato', 'sopra 1 resta «adeguata»: il modello ha due sole letture')
        self.assertTrue(first['nurse_over'], 'il superamento del riferimento resta disponibile come indicatore')
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
        # Turni mattina nella sede in tutto il mese: Anna 5, 6 e 7 + Beatrice 5 = 4 (Carla fuori sede esclusa); medici: Luca il 5.
        self.assertEqual((m['days'], m['nurse_shifts'], m['doctor_shifts']), (2, 4, 1))
        # Nei soli giorni con pazienti (5 e 6): 3 turni infermieristici e 1 medico → denominatore del rapporto.
        self.assertEqual((m['nurse_rated_shifts'], m['doctor_rated_shifts']), (3, 1))
        self.assertEqual((m['ordinary'], m['isolated'], m['patients']), (13, 1, 14))
        self.assertAlmostEqual(m['nurse_ratio'], (13 + 1 * 5) / 3)
        self.assertAlmostEqual(m['nurse_efficiency'], 1.2)
        self.assertEqual(m['nurse_level'], 'adeguato')
        self.assertAlmostEqual(m['doctor_ratio'], 14.0)
        self.assertAlmostEqual(m['doctor_efficiency'], 0.7)
        self.assertEqual(m['doctor_level'], 'sotto')
        p = by_slot['p']
        self.assertEqual((p['days'], p['nurse_shifts'], p['doctor_shifts'], p['patients']), (1, 1, 0, 5))
        self.assertEqual((p['nurse_rated_shifts'], p['doctor_rated_shifts']), (1, 0))
        self.assertAlmostEqual(p['nurse_ratio'], 5.0)
        self.assertEqual(p['nurse_level'], 'adeguato')
        self.assertIsNone(p['doctor_ratio'])
        self.assertEqual(p['doctor_level'], 'nessuno', 'nessun medico in turno nel pomeriggio')
        s = by_slot['s']
        self.assertEqual((s['days'], s['nurse_shifts'], s['patients']), (0, 0, 0))
        self.assertIsNone(s['nurse_ratio'])
        self.assertEqual(s['nurse_level'], 'nessuno')
        # Complessivi: «Totale turni da lavorare» (tutti i turni nella sede) e «Totale dialisi da effettuare».
        self.assertEqual((summary['nurse_shifts'], summary['doctor_shifts']), (5, 1))
        self.assertEqual((summary['nurse_rated_shifts'], summary['doctor_rated_shifts']), (4, 1))
        self.assertEqual((summary['ordinary'], summary['isolated'], summary['patients'], summary['days']), (18, 1, 19, 2))
        # «Media parametro»: media dei rapporti delle fasce con dati (mattina 6,0 e pomeriggio 5,0).
        self.assertAlmostEqual(summary['nurse_parameter'], 5.5)
        self.assertAlmostEqual(summary['nurse_efficiency'], 1.1)
        self.assertEqual(summary['nurse_level'], 'adeguato')
        self.assertAlmostEqual(summary['doctor_parameter'], 14.0)
        self.assertAlmostEqual(summary['doctor_efficiency'], 0.7)
        self.assertEqual(summary['doctor_level'], 'sotto')
        self.assertEqual((summary['threshold'], summary['nurse_reference'], summary['doctor_reference'],
                          summary['isolation_weight']), (0.92, 5, 20, 5))
        self.assertEqual((summary['dialysis_stations'], summary['isolation_stations']), (0, 0))

    def test_partial_month_summary_agrees_with_daily_rows(self):
        # Rilievo: 10 turni mattina dal 5 al 14, pazienti registrati solo il 5 e il 6 (5 ciascuno).
        for day in range(5, 15):
            self.assertEqual(self.entry(self.manager, day=f'2026-10-{day:02d}', person=self.anna).status, 200)
        self.patients('2026-10-05', 'm', 5)
        self.patients('2026-10-06', 'm', 5)
        snap = self.snap()
        for row in snap['workload']:
            self.assertAlmostEqual(row['nurse_ratio'], 5.0)
            self.assertAlmostEqual(row['nurse_efficiency'], 1.0)
            self.assertEqual(row['nurse_level'], 'adeguato')
        summary = snap['workload_summary']
        m = self.slot(summary, 'm')
        self.assertEqual((m['days'], m['nurse_shifts'], m['nurse_rated_shifts'], m['patients']), (2, 10, 2, 10))
        self.assertAlmostEqual(m['nurse_ratio'], 5.0, msg='stessi giorni al numeratore e al denominatore')
        self.assertAlmostEqual(m['nurse_efficiency'], 1.0)
        self.assertEqual(m['nurse_level'], 'adeguato')
        self.assertAlmostEqual(summary['nurse_parameter'], 5.0)
        self.assertAlmostEqual(summary['nurse_efficiency'], 1.0)
        self.assertEqual(summary['nurse_level'], 'adeguato')
        self.assertEqual(summary['nurse_shifts'], 10, 'il totale dei turni da lavorare conta tutto il mese')
        # Completando i pazienti il risultato non cambia: 10 giorni × 5 pazienti / 10 turni.
        for day in range(7, 15):
            self.patients(f'2026-10-{day:02d}', 'm', 5)
        m = self.slot(self.snap()['workload_summary'], 'm')
        self.assertEqual((m['days'], m['nurse_rated_shifts']), (10, 10))
        self.assertAlmostEqual(m['nurse_ratio'], 5.0)

    def test_summary_without_patients_has_no_ratio_but_counts_shifts(self):
        self.assertEqual(self.entry(self.manager, day='2026-10-05', person=self.anna).status, 200)
        summary = self.snap()['workload_summary']
        m = self.slot(summary, 'm')
        self.assertEqual((m['days'], m['nurse_shifts'], m['nurse_rated_shifts'], m['patients']), (0, 1, 0, 0))
        self.assertIsNone(m['nurse_ratio'])
        self.assertEqual(m['nurse_level'], 'senza_dati', 'turni senza pazienti registrati: non è «nessuno in turno»')
        self.assertEqual(m['doctor_level'], 'nessuno', 'nessun medico in turno')
        self.assertIsNone(summary['nurse_parameter'])
        self.assertEqual(summary['nurse_shifts'], 1)
        self.assertEqual((summary['nurse_level'], summary['doctor_level']), ('senza_dati', 'nessuno'))

    def test_missing_patients_is_told_apart_from_nobody_on_shift(self):
        # Rilievo: 5 turni infermieristici e 5 medici senza pazienti → «pazienti da registrare», non «nessuno in turno».
        for day in range(5, 10):
            self.assertEqual(self.entry(self.manager, day=f'2026-10-{day:02d}', person=self.anna).status, 200)
            self.assertEqual(self.entry(self.manager, day=f'2026-10-{day:02d}', person=self.luca).status, 200)
        summary = self.snap()['workload_summary']
        m = self.slot(summary, 'm')
        self.assertEqual((m['nurse_shifts'], m['doctor_shifts'], m['days']), (5, 5, 0))
        self.assertEqual((m['nurse_level'], m['doctor_level']), ('senza_dati', 'senza_dati'))
        self.assertEqual((summary['nurse_level'], summary['doctor_level']), ('senza_dati', 'senza_dati'))
        # Pazienti registrati in una fascia dove nessuno era in turno: riga e fascia dicono «nessuno in turno».
        self.patients('2026-10-05', 's', 6)
        snap = self.snap()
        row = snap['workload'][0]
        self.assertEqual((row['slot'], row['nurses'], row['doctors']), ('s', 0, 0))
        self.assertEqual((row['nurse_level'], row['doctor_level']), ('nessuno', 'nessuno'))
        self.assertTrue(row['uncovered'])
        s = self.slot(snap['workload_summary'], 's')
        self.assertEqual((s['days'], s['nurse_shifts'], s['nurse_level'], s['doctor_level']), (1, 0, 'nessuno', 'nessuno'))
        # Mese senza alcun turno nella sede: «nessuno in turno» anche nei complessivi.
        empty = self.snap(self.portal.admin, cid=self.portal.center('Centro Vuoto', 'VUOTO'))['workload_summary']
        self.assertEqual((empty['nurse_shifts'], empty['nurse_level'], empty['doctor_level']), (0, 'nessuno', 'nessuno'))

    def test_efficiency_has_two_readings_like_the_exported_sheet(self):
        cfg = {'efficiency_threshold': 0.92}
        self.assertEqual([efficiency_level(x, cfg) for x in (0.0, 0.91, 0.92, 1.0, 1.0001, 5.95, None)],
                         ['sotto', 'sotto', 'adeguato', 'adeguato', 'adeguato', 'adeguato', 'nessuno'])
        self.assertEqual(summary_level(None, 3, cfg), 'senza_dati')
        self.assertEqual(summary_level(None, 0, cfg), 'nessuno')
        self.assertEqual(summary_level(1.4, 3, cfg), 'adeguato')
        # Dal portale: un solo infermiere con 30 pazienti → efficienza 6,0, letta «adeguata» come nel foglio (verde).
        self.assertEqual(self.entry(self.manager, day='2026-10-05', person=self.anna).status, 200)
        self.patients('2026-10-05', 'm', 30)
        snap = self.snap()
        row = snap['workload'][0]
        self.assertAlmostEqual(row['nurse_efficiency'], 6.0)
        self.assertEqual(row['nurse_level'], 'adeguato')
        self.assertTrue(row['nurse_over'])
        self.assertEqual(self.slot(snap['workload_summary'], 'm')['nurse_level'], 'adeguato')
        self.assertEqual(snap['workload_summary']['nurse_level'], 'adeguato')
        self.assertNotIn('oltre', {r['nurse_level'] for r in snap['workload']} | {s['nurse_level'] for s in snap['workload_summary']['slots']})

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
        self.workload_url = f'/api/attendance/{self.cid}/{MONTH}/workload'

    def fill(self):
        WorkloadIndicators.fill(self)

    def patients(self, day, slot, ordinary, isolated=0):
        WorkloadIndicators.patients(self, day, slot, ordinary, isolated)

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
        self.assertEqual((anna['shifts'], anna['external'], anna['festive'], anna['absences'], anna['total'], anna['registrations']),
                         (4, 0, 1, 0, 4, 4))
        self.assertEqual(anna['codes']['FE'], 0)
        self.assertEqual(anna['group'], 'infermieri')
        bea = by_name['Beatrice Neri']
        self.assertEqual((bea['shifts'], bea['absences'], bea['codes']['FE'], bea['total'], bea['registrations']), (1, 1, 1, 2, 2))
        carla = by_name['Carla Rossi']
        self.assertEqual((carla['shifts'], carla['external'], carla['total']), (1, 1, 1))
        luca = by_name['Luca Verdi']
        self.assertEqual((luca['shifts'], luca['group'], luca['total']), (1, 'medici', 1))
        groups = {g['id']: g for g in counters['groups']}
        self.assertEqual(list(groups), ['infermieri', 'medici', 'tutti'], 'i gruppi vuoti non compaiono; il totale sempre')
        nurses = groups['infermieri']
        self.assertEqual((nurses['people'], nurses['shifts'], nurses['external'], nurses['festive'], nurses['codes']['FE'],
                          nurses['total'], nurses['registrations']), (3, 6, 1, 1, 1, 7, 7))
        self.assertEqual((groups['medici']['people'], groups['medici']['shifts']), (1, 1))
        everyone = groups['tutti']
        self.assertEqual(everyone['label'], 'Tutto il personale')
        self.assertEqual((everyone['people'], everyone['shifts'], everyone['external'], everyone['codes']['FE'], everyone['total'],
                          everyone['registrations']), (4, 7, 1, 1, 8, 8))

    def test_total_leaves_out_rc_and_rest_like_the_model(self):
        # Rilievo: 2 turni, ferie, un recupero turno e un riposo → il totale del file è 3 (93 − vuote − RC), le registrazioni 5.
        self.assertEqual(self.entry(self.manager, day='2026-10-05', person=self.anna).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-06', person=self.anna).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-07', code='FE', person=self.anna).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-08', code='RC', person=self.anna).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-09', code='R', person=self.anna).status, 200)
        counters = self.snap()['counters']
        anna = next(r for r in counters['people'] if r['person_id'] == self.anna)
        self.assertEqual((anna['shifts'], anna['absences'], anna['codes']['FE'], anna['codes']['RC'], anna['codes']['R']), (2, 2, 1, 1, 1))
        self.assertEqual((anna['total'], anna['registrations']), (3, 5))
        groups = {g['id']: g for g in counters['groups']}
        self.assertEqual((groups['infermieri']['total'], groups['infermieri']['registrations']), (3, 5))
        self.assertEqual((groups['tutti']['total'], groups['tutti']['registrations'], groups['tutti']['codes']['RC']), (3, 5, 1))
        # Stessa base delle unità della proposta di accordo («Accordi e calcoli»: turni + causali conteggiate, RC escluso).
        report = self.manager.ok('GET', f'/api/agreements/{self.cid}/{MONTH}')
        row = next(r for r in report['rows'] if r['person_id'] == self.anna)
        self.assertEqual(row['units'], anna['total'])
        # Una persona con soli riposi e recuperi resta in elenco con totale 0.
        self.assertEqual(self.entry(self.manager, day='2026-10-05', code='R', person=self.bea).status, 200)
        bea = next(r for r in self.snap()['counters']['people'] if r['person_id'] == self.bea)
        self.assertEqual((bea['total'], bea['registrations'], bea['codes']['R']), (0, 1, 1))

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
