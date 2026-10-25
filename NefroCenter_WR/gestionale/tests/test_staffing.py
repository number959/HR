import unittest

from test_attendance import MONTH, AttendanceCase


class Coverage(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.hr = self.portal.user('hrcentrale', 'hr')
        self.viewer = self.portal.user('direzione', 'viewer', [self.cid])
        self.url = f'/api/staffing/{self.cid}/{MONTH}'

    def requirements(self, weekly):
        req = self.manager.ok('GET', self.url)['requirements']
        return self.manager.put(f'/api/staffing/{self.cid}/requirements', {'version': req['version'], 'weekly': weekly})

    def test_requirements_and_states(self):
        self.assertStatus(self.operator.put(f'/api/staffing/{self.cid}/requirements', {'version': 0, 'weekly': []}), 403)
        self.assertEqual(self.requirements([{'weekday': 0, 'slot': 'm', 'role': 'INF', 'minimum': 2}]).status, 200)
        self.entry(self.manager, day='2026-10-05', layer='planned')  # lunedì
        report = self.manager.ok('GET', self.url)
        monday = next(r for r in report['rows'] if r['day'] == '2026-10-05' and r['slot'] == 'm')
        self.assertEqual((monday['minimum'], monday['planned'], monday['gap'], monday['state']), (2, 1, 1, 'uncovered'))
        self.assertEqual(report['summary']['uncovered'], 4, 'quattro lunedì in ottobre 2026 scoperti')
        duplicate = self.requirements([{'weekday': 0, 'slot': 'm', 'role': 'INF', 'minimum': 1}] * 2)
        self.assertStatus(duplicate, 400, 'ripetuto')

    def test_viewer_sees_aggregates_only(self):
        self.entry(self.manager, day='2026-10-05', layer='planned')
        report = self.viewer.ok('GET', self.url)
        self.assertEqual(report['people'], [])
        self.assertEqual(report['availability'], [])
        self.assertFalse(report['permissions']['propose'])

    def test_unavailable_planned_shift_is_excluded(self):
        self.entry(self.manager, day='2026-10-05', layer='planned')
        self.hr.ok('PUT', f'/api/staffing/{self.cid}/availability/{self.anna}',
                   {'version': 0, 'start': '2026-10-05', 'end': '2026-10-06', 'status': 'unavailable', 'note': 'Corso'})
        report = self.manager.ok('GET', self.url)
        row = next(r for r in report['rows'] if r['day'] == '2026-10-05')
        self.assertEqual((row['planned'], row['excluded']), (0, 1))
        self.assertTrue(report['problems'])
        overlap = self.hr.put(f'/api/staffing/{self.cid}/availability/{self.anna}',
                              {'version': 0, 'start': '2026-10-06', 'end': '2026-10-07', 'status': 'available'})
        self.assertStatus(overlap, 400, 'sovrapposto')


class Substitutions(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.hr = self.portal.user('hrcentrale', 'hr')
        self.west = self.portal.center('Centro Ovest', 'OVEST')
        self.portal.step_up(self.admin)
        self.twin = self.admin.ok('POST', f'/api/centers/{self.west}/people', {'name': 'Anna Bianchi', 'role': 'INF'})['id']
        groups = self.hr.ok('GET', '/api/workforce')['groups']
        target = next(g for g in groups if any(a['person_id'] == self.anna for a in g['assignments']))
        twin = next(a for g in groups for a in g['assignments'] if a['person_id'] == self.twin)
        self.portal.step_up(self.hr)
        self.hr.ok('POST', f'/api/workforce/{self.west}/{self.twin}/link',
                   {'identity_id': target['identity_id'], 'identity_version': target['version'], 'version': twin['version'],
                    'reason': 'Stessa persona verificata'})

    def propose(self, day='2026-10-08', slot='p'):
        return self.hr.post(f'/api/staffing/{self.cid}/substitutions',
                            {'person_id': self.anna, 'origin_center_id': self.west, 'origin_person_id': self.twin,
                             'day': day, 'slot': slot, 'code': slot, 'note': 'Copertura per assenza imprevista'})

    def test_accepted_substitution_creates_planned_shift(self):
        proposal = self.propose()
        self.assertEqual(proposal.status, 200, proposal.body)
        decided = self.manager.ok('POST', f'/api/staffing/{self.cid}/substitutions/{proposal.data["id"]}',
                                  {'decision': 'accept', 'note': 'Accettata dal responsabile', 'version': 1})
        self.assertEqual(decided['status'], 'accepted')
        planned = [e for e in self.snap()['entries'] if e['layer'] == 'planned']
        self.assertEqual([(e['day'], e['slot'], e['source']) for e in planned], [('2026-10-08', 'p', 'sostituzione')])
        self.assertStatus(self.manager.post(f'/api/staffing/{self.cid}/substitutions/{proposal.data["id"]}',
                                            {'decision': 'accept', 'note': 'Seconda accettazione', 'version': 1}), 409)

    def test_changed_data_blocks_acceptance(self):
        proposal = self.propose().data
        self.admin.ok('POST', f'/api/attendance/{self.west}/{MONTH}/entries',
                      dict(person_id=self.twin, day='2026-10-08', slot='m', code='m', layer='planned'))
        response = self.manager.post(f'/api/staffing/{self.cid}/substitutions/{proposal["id"]}',
                                     {'decision': 'accept', 'note': 'Tentativo dopo modifiche', 'version': 1})
        self.assertStatus(response, 409, 'cambiati')

    def test_unlinked_people_cannot_be_proposed(self):
        other = self.manager.ok('POST', f'/api/centers/{self.cid}/people', {'name': 'Mario Rossi', 'role': 'INF'})['id']
        response = self.hr.post(f'/api/staffing/{self.cid}/substitutions',
                                {'person_id': other, 'origin_center_id': self.west, 'origin_person_id': self.twin,
                                 'day': '2026-10-08', 'slot': 'p', 'code': 'p', 'note': 'Persona non collegata'})
        self.assertStatus(response, 400, 'collegate')

    def test_operator_cannot_propose_or_decide(self):
        self.assertStatus(self.operator.post(f'/api/staffing/{self.cid}/substitutions', {}), 403)


if __name__ == '__main__':
    unittest.main()
