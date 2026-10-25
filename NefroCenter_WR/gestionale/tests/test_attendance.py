import copy
import unittest

from support import PortalCase

MONTH = '2026-10'


class AttendanceCase(PortalCase):
    def setUp(self):
        super().setUp()
        self.cid = self.portal.center('Centro Dialisi Est', 'EST')
        self.manager = self.portal.user('responsabile', 'manager', [self.cid])
        self.operator = self.portal.user('compilatore', 'operator', [self.cid])
        self.anna = self.person('Anna Bianchi', 'INF', 'M001')
        self.luca = self.person('Luca Verdi', 'MED', 'M002')

    def person(self, name, role, registration='', client=None):
        client = client or self.manager
        return client.ok('POST', f'/api/centers/{self.cid}/people', {'name': name, 'role': role,
                                                                     'registration': registration})['id']

    def snap(self, client=None, cid=None):
        return (client or self.manager).ok('GET', f'/api/attendance/{cid or self.cid}/{MONTH}')

    def entry(self, client, day='2026-10-05', slot='m', code='m', person=None, layer='actual', **extra):
        body = dict(person_id=person or self.anna, day=day, slot=slot, code=code, layer=layer, **extra)
        return client.post(f'/api/attendance/{self.cid}/{MONTH}/entries', body)

    def config(self):
        return self.manager.ok('GET', f'/api/centers/{self.cid}/config')

    def save_config(self, change):
        current = self.config()
        cfg = copy.deepcopy(current['config'])
        change(cfg)
        self.portal.step_up(self.manager)
        return self.manager.put(f'/api/centers/{self.cid}/config', {'config': cfg, 'version': current['version']})


class Registry(AttendanceCase):
    def test_operator_records_shift_with_slot_times(self):
        saved = self.entry(self.operator)
        self.assertEqual(saved.status, 200, saved.body)
        entry = saved.data['entry']
        self.assertEqual((entry['start'], entry['end'], entry['kind']), ('07:00', '13:00', 'work'))
        snap = self.snap(self.operator)
        row = next(r for r in snap['summary'] if r['person_id'] == self.anna)
        self.assertEqual((row['shifts'], row['minutes']), (1, 360))
        self.assertTrue(snap['editable'])

    def test_operator_cannot_change_times_unless_enabled(self):
        self.assertStatus(self.entry(self.operator, start='08:00', end='13:00'), 403, 'bloccati')
        self.assertEqual(self.entry(self.manager, start='08:00', end='13:00').status, 200)
        self.assertEqual(self.save_config(lambda c: c.update(operator_edit_times=True)).status, 200)
        self.assertEqual(self.entry(self.operator, day='2026-10-06', start='07:30', end='13:00').status, 200)

    def test_overlap_and_rest_warning(self):
        self.assertEqual(self.entry(self.manager, day='2026-10-05', slot='n', code='n').status, 200)
        # Notte 21:00-07:00 e mattina successiva 07:00: riposo zero → avviso, non errore.
        warning = self.entry(self.manager, day='2026-10-06', slot='m', code='m')
        self.assertEqual(warning.status, 200)
        self.assertTrue(any('Riposo inferiore' in w for w in warning.data['warnings']))
        overlap = self.entry(self.manager, day='2026-10-05', slot='s', code='s')
        self.assertStatus(overlap, 400, 'Sovrapposizione')
        again = self.entry(self.manager, day='2026-10-05', slot='n', code='n')
        self.assertStatus(again, 400, 'già compilata')

    def test_absence_and_codes_by_slot(self):
        self.assertStatus(self.entry(self.operator, slot='m', code='p'), 400, 'non è prevista')
        absence = self.entry(self.operator, slot='m', code='FE')
        self.assertEqual(absence.status, 200)
        self.assertEqual(absence.data['entry']['kind'], 'absence')
        row = next(r for r in self.snap()['summary'] if r['person_id'] == self.anna)
        self.assertEqual((row['absences'], row['causes']), (1, {'FE': 1}))

    def test_planned_layer_and_pending(self):
        self.assertEqual(self.entry(self.operator, layer='planned', day='2026-10-07').status, 200)
        snap = self.snap()
        self.assertEqual(next(r for r in snap['summary'] if r['person_id'] == self.anna)['pending'], 1)
        self.assertTrue(any('da consuntivare' in a['text'] for a in snap['alerts']))
        self.assertEqual(self.save_config(lambda c: c.update(operator_planned=False)).status, 200)
        self.assertStatus(self.entry(self.operator, layer='planned', day='2026-10-08'), 403, 'Pianificazione')

    def test_edit_needs_current_version_and_delete_rules(self):
        entry = self.entry(self.operator).data['entry']
        url = f'/api/attendance/{self.cid}/{MONTH}/entries'
        edited = self.operator.post(url, {'id': entry['id'], 'version': entry['version'], 'person_id': self.anna,
                                          'day': entry['day'], 'slot': 'm', 'layer': 'actual', 'code': 'm', 'note': 'Ok'})
        self.assertEqual(edited.status, 200)
        stale = self.operator.post(url, {'id': entry['id'], 'version': entry['version'], 'person_id': self.anna,
                                         'day': entry['day'], 'slot': 'm', 'layer': 'actual', 'code': 'm'})
        self.assertStatus(stale, 409)
        moved = self.operator.post(url, {'id': entry['id'], 'version': 2, 'person_id': self.anna, 'day': '2026-10-09',
                                         'slot': 'm', 'layer': 'actual', 'code': 'm'})
        self.assertStatus(moved, 400, 'eliminarla')
        self.assertEqual(self.save_config(lambda c: c.update(operator_delete=False)).status, 200)
        self.assertStatus(self.operator.delete(f'{url}/{entry["id"]}', {'version': 2}), 403)
        self.manager.ok('DELETE', f'{url}/{entry["id"]}', {'version': 2})

    def test_roles_without_write_access(self):
        hr = self.portal.user('hrcentrale', 'hr')
        viewer = self.portal.user('direzione', 'viewer', [self.cid])
        self.assertEqual(self.snap(hr)['center']['id'], self.cid)
        self.assertStatus(self.entry(hr), 403)
        self.assertStatus(self.entry(viewer), 403)
        self.assertFalse(self.snap(viewer)['editable'])
        other = self.portal.center('Centro Ovest', 'OVEST')
        self.assertStatus(self.operator.get(f'/api/attendance/{other}/{MONTH}'), 403, 'non assegnata')

    def test_private_person_fields_hidden_from_operator(self):
        self.manager.ok('PUT', f'/api/centers/{self.cid}/people/{self.anna}',
                        {'note': 'Accordo riservato', 'version': 1,
                         'pay_override': {'weekday_rate': 60, 'holiday_rate': 80, 'fixed_deduction': 0, 'ccnl_rate': 70,
                                          'pay_mode': 'all'}})
        person = next(p for p in self.snap(self.operator)['people'] if p['id'] == self.anna)
        self.assertNotIn('note', person)
        self.assertNotIn('pay_override', person)
        person = next(p for p in self.snap(self.manager)['people'] if p['id'] == self.anna)
        self.assertEqual(person['pay_override']['weekday_rate'], 60)

    def test_registration_is_unique_and_operator_cannot_add_people(self):
        response = self.manager.post(f'/api/centers/{self.cid}/people', {'name': 'Altra', 'role': 'INF', 'registration': 'M001'})
        self.assertStatus(response, 400, 'Matricola')
        self.assertStatus(self.operator.post(f'/api/centers/{self.cid}/people', {'name': 'X', 'role': 'INF'}), 403)
        self.assertStatus(self.manager.post(f'/api/centers/{self.cid}/people', {'name': 'X', 'role': 'NONESISTE'}), 400)


class MonthLifecycle(AttendanceCase):
    def month_action(self, client, action, body):
        return client.post(f'/api/attendance/{self.cid}/{MONTH}/{action}', body)

    def test_verify_close_reopen(self):
        self.entry(self.operator)
        state = self.snap()['state']
        self.assertStatus(self.month_action(self.manager, 'close', {'version': state['version']}), 400, 'Verificare calendario')
        self.assertStatus(self.month_action(self.operator, 'verify', {'verified': True, 'version': state['version']}), 403)
        state = self.month_action(self.manager, 'verify', {'verified': True, 'version': state['version']}).data['state']
        closed = self.month_action(self.manager, 'close', {'version': state['version']})
        self.assertEqual(closed.status, 200, closed.body)
        self.assertStatus(self.entry(self.operator, day='2026-10-12'), 400, 'Mese chiuso')
        self.assertFalse(self.snap(self.operator)['editable'])
        state = closed.data['state']
        self.assertStatus(self.month_action(self.manager, 'reopen', {'version': state['version'], 'reason': 'breve'}), 400)
        reopened = self.month_action(self.manager, 'reopen', {'version': state['version'], 'reason': 'Correzione turno del 5'})
        self.assertEqual(reopened.status, 200)
        self.assertEqual(self.entry(self.operator, day='2026-10-12').status, 200)

    def test_close_blocked_by_pending_plan_and_missing_times(self):
        # Il mese adotta i parametri in vigore alla prima registrazione.
        self.assertEqual(self.save_config(lambda c: c.update(require_times_on_close=True)).status, 200)
        self.entry(self.manager)
        self.entry(self.manager, day='2026-10-20', layer='planned')
        state = self.snap()['state']
        state = self.month_action(self.manager, 'verify', {'verified': True, 'version': state['version']}).data['state']
        self.assertStatus(self.month_action(self.manager, 'close', {'version': state['version']}), 400, 'pianificate')
        self.entry(self.manager, day='2026-10-20')
        self.entry(self.manager, day='2026-10-21', start='', end='')
        self.assertStatus(self.month_action(self.manager, 'close', {'version': state['version']}), 400, 'orari')

    def test_rules_version_is_kept_per_month(self):
        self.entry(self.operator)
        self.assertEqual(self.save_config(lambda c: c['slots'][0].update(start='06:30')).status, 200)
        snap = self.snap()
        self.assertTrue(snap['rules_outdated'])
        self.assertEqual(snap['config']['slots'][0]['start'], '07:00', 'il mese compilato mantiene i suoi parametri')
        state = snap['state']
        refused = self.month_action(self.manager, 'apply-rules', {'version': state['version'], 'reason': 'Nuovi orari del centro'})
        self.assertStatus(refused, 400, 'contiene registrazioni')
        november = self.manager.ok('GET', f'/api/attendance/{self.cid}/2026-11')
        self.assertEqual(november['config']['slots'][0]['start'], '06:30')

    def test_operator_flags_follow_current_config_even_on_old_months(self):
        self.entry(self.operator)
        self.assertEqual(self.save_config(lambda c: c.update(operator_delete=False)).status, 200)
        caps = self.snap(self.operator)['caps']
        self.assertFalse(caps['presenze.elimina'])

    def test_config_validation(self):
        bad = self.save_config(lambda c: c['slots'][0].update(start='13:00', end='07:00'))
        self.assertStatus(bad, 400, 'giorno dopo')
        bad = self.save_config(lambda c: c.update(nurse_roles=['MED']))
        self.assertStatus(bad, 400, 'sia infermieristico sia medico')
        self.assertStatus(self.operator.put(f'/api/centers/{self.cid}/config', {'config': {}, 'version': 1}), 403)


class Export(AttendanceCase):
    def test_csv_export_escapes_formulas_and_respects_flag(self):
        evil = self.person('=HYPERLINK("http://x")', 'INF')
        self.entry(self.operator, person=evil)
        response = self.operator.get(f'/api/attendance/{self.cid}/{MONTH}/export.csv')
        self.assertEqual(response.status, 200)
        text = response.body.decode('utf-8-sig')
        self.assertIn("'=HYPERLINK", text)
        self.assertIn('attachment;', response.header('Content-Disposition'))
        detail = self.operator.get(f'/api/attendance/{self.cid}/{MONTH}/export.csv?detail=1').body.decode('utf-8-sig')
        self.assertIn('Centro Dialisi Est', detail)
        self.assertEqual(self.save_config(lambda c: c.update(operator_export=False)).status, 200)
        self.assertStatus(self.operator.get(f'/api/attendance/{self.cid}/{MONTH}/export.csv'), 403)
        self.assertEqual(self.manager.get(f'/api/attendance/{self.cid}/{MONTH}/export.csv').status, 200)


class LinkedIdentity(AttendanceCase):
    def test_overlap_detected_across_centers_for_same_identity(self):
        other = self.portal.center('Centro Ovest', 'OVEST')
        self.portal.step_up(self.admin)
        twin = self.admin.ok('POST', f'/api/centers/{other}/people', {'name': 'Anna Bianchi', 'role': 'INF'})['id']
        with self.portal.db.write() as con:
            identity = con.execute('SELECT identity_id FROM people WHERE id=?', (self.anna,)).fetchone()[0]
            con.execute('UPDATE people SET identity_id=? WHERE id=?', (identity, twin))
        self.admin.ok('POST', f'/api/attendance/{other}/{MONTH}/entries',
                      dict(person_id=twin, day='2026-10-05', slot='m', code='m', layer='actual'))
        clash = self.entry(self.manager, slot='m')
        self.assertStatus(clash, 400, 'Centro Ovest')


class Workload(AttendanceCase):
    def test_patients_and_ratios(self):
        self.entry(self.manager)
        self.entry(self.manager, person=self.luca)
        url = f'/api/attendance/{self.cid}/{MONTH}/workload'
        self.assertStatus(self.operator.put(url, {'day': '2026-10-05', 'slot': 'm', 'ordinary': 8, 'isolated': 1}), 403)
        self.manager.ok('PUT', url, {'day': '2026-10-05', 'slot': 'm', 'ordinary': 8, 'isolated': 1})
        row = self.snap()['workload'][0]
        self.assertEqual((row['nurses'], row['doctors']), (1, 1))
        self.assertEqual(row['nurse_ratio'], 13)
        self.assertTrue(row['nurse_over'])
        self.assertEqual(row['doctor_ratio'], 9)


if __name__ == '__main__':
    unittest.main()
