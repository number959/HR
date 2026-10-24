"""Copertura: conteggi indipendenti, confini di sede e decisioni atomiche."""
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import core
import staffing
import workforce
import test_structures


class StaffingTests(unittest.TestCase):
    tearDown = test_structures.StructureTests.tearDown
    user = test_structures.StructureTests.user

    def setUp(self):
        test_structures.StructureTests.setUp(self)
        staffing.init(core)
        self.both = self.user('referenteduesedi', 'manager', [self.one, self.two])
        self.ids = {}
        for cid in (self.one, self.two):
            core.mutate(self.admin, 'person', {**self.req(cid), 'person': {
                'name': 'Persona di prova', 'registration': 'PROVA1', 'role': 'INF', 'active': True}})
            with core.connect() as c:
                self.ids[cid] = core.objects(c, 'people', cid)[0]['id']
        self.link()

    def req(self, cid=None, month='2026-10'):
        cid = cid or self.one
        with core.connect() as c:
            return dict(cid=cid, month=month, revision=core.center(c, cid)['revision'])

    def link(self):
        with core.connect() as c:
            source = workforce._assignment(c, self.two, self.ids[self.two])
            target = workforce._assignment(c, self.one, self.ids[self.one])
            version = c.execute('SELECT version FROM group_people WHERE id=?', (target['global_id'],)).fetchone()[0]
        workforce.mutate(core, self.hr, 'workforce_link', dict(
            cid=self.two, pid=self.ids[self.two], assignment_version=source['version'],
            global_id=target['global_id'], target_version=version, reason='Identità verificata nelle due strutture'))

    def proposal(self, user=None, **fields):
        body = dict(
            cid=self.one, pid=self.ids[self.one], origin_cid=self.two, origin_pid=self.ids[self.two],
            day='2026-10-05', slot='m', code='m', note='Copertura concordata della mattina')
        body.update(fields)
        return staffing.propose(core, user or self.hr, body)

    def decision(self, proposal, user=None, **fields):
        body = dict(
            id=proposal['id'], version=proposal['version'], decision='accept',
            note='Disponibilità e fascia verificate')
        body.update(fields)
        return staffing.decide(core, user or self.manager, body)

    def availability(self, cid=None, user=None, **fields):
        cid = cid or self.one
        body = dict(cid=cid, pid=self.ids[cid], version=0, **{'from': '2026-10-05', 'to': '2026-10-05'},
                    status='unavailable', note='Nota organizzativa riservata', active=True)
        body.update(fields)
        return staffing.save_availability(core, user or self.hr, body)['availability']

    def entry(self, cid=None, **fields):
        cid = cid or self.one
        raw = dict(person_id=self.ids[cid], day='2026-10-05', slot='m', code='m', layer='planned')
        raw.update(fields)
        return core.mutate(self.admin, 'entry', {**self.req(cid, raw['day'][:7]), 'entry': raw})

    def test_requirements_dates_override_weekdays_and_report_independent_layers(self):
        staffing.save_requirements(core, self.manager, dict(cid=self.one, version=0,
            weekly=[dict(weekday=0, slot='m', role='INF', minimum=2)],
            overrides=[dict(day='2026-10-12', slot='m', role='INF', minimum=0)]))
        self.entry()
        self.entry(layer='actual')
        report = staffing.report(core, self.operator, self.one, '2026-10')
        rows = {r['day']: r for r in report['rows']}
        self.assertEqual((rows['2026-10-05']['planned'], rows['2026-10-05']['actual'], rows['2026-10-05']['gap']), (1, 1, 1))
        self.assertEqual((rows['2026-10-12']['minimum'], rows['2026-10-12']['gap'], rows['2026-10-12']['state']), (0, 0, 'covered'))
        self.assertEqual(report['summary'], dict(configured=4, uncovered=3, missing=5))
        for key in ('availability', 'proposals', 'candidates', 'problems', 'people'):
            self.assertEqual(report[key], [])
        self.assertFalse(report['permissions']['configure'])

    def test_effective_role_and_conflicts_change_coverage_not_registry(self):
        with core.connect() as c:
            assignment = workforce._assignment(c, self.one, self.ids[self.one])
        workforce.mutate(core, self.hr, 'workforce_contract', dict(cid=self.one, pid=self.ids[self.one],
            assignment_version=assignment['version'], reason='Cambio qualifica documentato',
            effective_from='2026-10-01', effective_to='', data=dict(role='MED', contract_type='Indeterminato',
            ccnl='Sanità', level='D', weekly_hours=36, part_time_percent=100)))
        self.entry()
        self.availability()
        report = staffing.report(core, self.manager, self.one, '2026-10')
        row = report['rows'][0]
        self.assertEqual((row['role'], row['planned'], row['excluded']), ('MED', 0, 1))
        self.assertEqual(len(report['problems']), 1)
        with core.connect() as c:
            self.assertEqual(len(core.objects(c, 'entries', self.one)), 1)
            self.assertEqual(core.objects(c, 'people', self.one)[0]['role'], 'INF')

    def test_permissions_scopes_and_current_roles(self):
        for user in (self.operator, self.viewer):
            with self.assertRaises(PermissionError): self.availability(user=user)
            with self.assertRaises(PermissionError): self.proposal(user=user)
            with self.assertRaises(PermissionError): staffing.report(core, user, self.two, '2026-10')
        with self.assertRaises(PermissionError): self.proposal(user=self.manager)
        with self.assertRaises(PermissionError): self.availability(cid=self.two, user=self.manager)
        with self.assertRaises(PermissionError): staffing.save_requirements(core, self.hr, dict(cid=self.one, version=0))
        proposal = self.proposal(user=self.both)
        with self.assertRaises(PermissionError): self.decision(proposal, user=self.hr)
        with core.connect() as c:
            c.execute("UPDATE users SET role='viewer' WHERE id=?", (self.manager['id'],)); c.commit()
        with self.assertRaises(PermissionError): self.decision(proposal)
        with core.connect() as c:
            c.execute('UPDATE users SET active=0 WHERE id=?', (self.hr['id'],)); c.commit()
        with self.assertRaises(core.AuthenticationError): self.availability()

    def test_acceptance_only_writes_planned_and_is_single_use(self):
        before = self.req()['revision']
        proposal = self.proposal()
        with core.connect() as c:
            self.assertEqual(core.objects(c, 'entries', self.one), [])
        result = self.decision(proposal)
        self.assertEqual((result['status'], result['version']), ('accepted', 2))
        with core.connect() as c:
            entries = core.objects(c, 'entries', self.one)
            self.assertEqual(len(entries), 1)
            self.assertEqual((entries[0]['layer'], entries[0]['start'], entries[0]['end']), ('planned', '07:00', '13:00'))
            self.assertEqual(entries[0]['id'], result['entry_id'])
            self.assertEqual(core.center(c, self.one)['revision'], before + 1)
            self.assertEqual(core.objects(c, 'entries', self.two), [])
        with self.assertRaises(ValueError): self.decision(proposal)

    def test_rejection_remains_possible_when_source_data_changes(self):
        proposal = self.proposal()
        self.availability(status='preferred')
        with self.assertRaisesRegex(ValueError, 'cambiati'): self.decision(proposal)
        result = staffing.decide(core, self.manager, dict(id=proposal['id'], version=1,
            decision='reject', note='Ripianificare dopo la modifica dei dati'))
        self.assertEqual(result['status'], 'rejected')
        with core.connect() as c:
            self.assertEqual(core.objects(c, 'entries', self.one), [])

    def test_failed_acceptance_rolls_back_entry_period_revision_and_decision(self):
        proposal = self.proposal()
        before = self.req()['revision']
        original = core.audit
        def failing_audit(c, user, action, *args, **kwargs):
            if action == 'Sostituzione valutata':
                raise RuntimeError('Errore simulato dopo la scrittura del turno')
            return original(c, user, action, *args, **kwargs)
        with patch.object(core, 'audit', side_effect=failing_audit), self.assertRaises(RuntimeError):
            self.decision(proposal)
        with core.connect() as c:
            self.assertEqual(core.objects(c, 'entries', self.one), [])
            self.assertEqual(core.center(c, self.one)['revision'], before)
            row = c.execute('SELECT * FROM staffing_proposals WHERE id=?', (proposal['id'],)).fetchone()
            self.assertEqual((row['status'], row['version'], row['entry_id']), ('pending', 1, ''))
        self.assertEqual(self.decision(proposal)['status'], 'accepted')

    def test_two_concurrent_decisions_create_one_shift(self):
        proposal = self.proposal()
        ready = threading.Barrier(2)
        def decide(_):
            ready.wait(timeout=5)
            try: return self.decision(proposal)
            except ValueError: return None
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(decide, range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        with core.connect() as c:
            self.assertEqual(len(core.objects(c, 'entries', self.one)), 1)

    def test_link_required_duplicate_pending_and_closed_month(self):
        proposal = self.proposal()
        with self.assertRaisesRegex(ValueError, 'già una proposta'): self.proposal()
        with core.connect() as c:
            ct = core.center(c, self.one); period = core.period(c, ct, '2026-10')
            period['closed'] = True; core.put_period(c, self.one, '2026-10', period); c.commit()
        with self.assertRaisesRegex(ValueError, 'chiuso'): self.decision(proposal)
        with core.connect() as c:
            period['closed'] = False; core.put_period(c, self.one, '2026-10', period)
            assignment = workforce._assignment(c, self.two, self.ids[self.two]); c.commit()
        workforce.mutate(core, self.hr, 'workforce_link', dict(cid=self.two, pid=self.ids[self.two],
            assignment_version=assignment['version'], global_id='', reason='Separazione dopo verifica identità'))
        with self.assertRaisesRegex(ValueError, 'collegate esplicitamente'): self.decision(proposal)

    def test_overnight_checks_next_day_unavailability_and_cross_center_overlap(self):
        self.availability(cid=self.two, **{'from': '2026-10-06', 'to': '2026-10-06'})
        body = dict(cid=self.one, pid=self.ids[self.one], origin_cid=self.two, origin_pid=self.ids[self.two],
            day='2026-10-05', slot='n', code='n', note='Copertura della notte verificata')
        with self.assertRaisesRegex(ValueError, 'non disponibile'): staffing.propose(core, self.hr, body)
        self.entry(cid=self.two, day='2026-10-07', slot='n', code='n')
        body.update(day='2026-10-07')
        with self.assertRaises(ValueError): staffing.propose(core, self.hr, body)
        self.entry(cid=self.two, day='2026-10-09', slot='n', code='R')
        body.update(day='2026-10-09')
        with self.assertRaises(ValueError): staffing.propose(core, self.hr, body)

    def test_missing_times_block_candidate_and_exclude_overlapping_coverage(self):
        self.entry(cid=self.two, start='', end='')
        with self.assertRaisesRegex(ValueError, 'orari'): self.proposal(slot='p', code='p')
        self.entry(day='2026-10-05', slot='p', code='p')
        report = staffing.report(core, self.manager, self.one, '2026-10')
        self.assertEqual((report['rows'][0]['planned'], report['rows'][0]['excluded']), (0, 1))

    def test_imported_local_ids_cannot_hide_cross_center_conflicts(self):
        self.entry()
        with core.connect() as c:
            existing = core.objects(c, 'entries', self.one)[0]
            core.put(c, 'entries', self.two, {**existing, 'person_id': self.ids[self.two],
                     'work_site': core.center(c, self.two)['name']})
            c.commit()
        report = staffing.report(core, self.manager, self.one, '2026-10')
        self.assertEqual((report['rows'][0]['planned'], report['rows'][0]['excluded']), (0, 1))

    def test_unavailability_never_erases_recorded_actual_attendance(self):
        self.entry()
        self.entry(layer='actual')
        self.availability()
        report = staffing.report(core, self.viewer, self.one, '2026-10')
        self.assertEqual((report['rows'][0]['planned'], report['rows'][0]['actual']), (0, 1))
        self.assertNotIn('Nota organizzativa riservata', core.dump(report))
        with core.connect() as c:
            self.assertEqual(len(core.objects(c, 'entries', self.one)), 2)

    def test_validation_versions_and_inclusive_availability_ranges(self):
        first = self.availability()
        with self.assertRaisesRegex(ValueError, 'sovrapposto'):
            self.availability(**{'from': '2026-10-04', 'to': '2026-10-05'})
        with self.assertRaisesRegex(ValueError, 'modificata'):
            self.availability(id=first['id'], version=0)
        self.availability(id=first['id'], version=1, active=False)
        self.availability(**{'from': '2026-10-04', 'to': '2026-10-05'})
        for fields in ({'version': True}, {'from': '2026-02-30'}, {'to': '2026-10-04'}, {'id': []}, {'active': 1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError): self.availability(**fields)
        for minimum in (True, -1, 1.5, 1001):
            with self.subTest(minimum=minimum), self.assertRaises(ValueError):
                staffing.save_requirements(core, self.manager, dict(cid=self.one, version=0,
                    weekly=[dict(weekday=0, slot='m', role='INF', minimum=minimum)]))
        with self.assertRaises(ValueError):
            staffing.save_requirements(core, self.manager, dict(cid=self.one, version=0,
                weekly=[dict(weekday=0, slot=[], role='INF', minimum=1)]))

    def test_approval_guard_blocks_atomic_acceptance(self):
        import approvals
        proposal = self.proposal()
        with patch.object(approvals, 'guard_mutation', side_effect=ValueError('Mese in approvazione')) as guard:
            with self.assertRaisesRegex(ValueError, 'approvazione'): self.decision(proposal)
        self.assertEqual(guard.call_args.args[3:], ('entry', {'cid': self.one, 'month': '2026-10'}))
        with core.connect() as c:
            self.assertEqual(core.objects(c, 'entries', self.one), [])
            self.assertEqual(c.execute('SELECT status FROM staffing_proposals WHERE id=?', (proposal['id'],)).fetchone()[0], 'pending')


if __name__ == '__main__':
    unittest.main(verbosity=2)
