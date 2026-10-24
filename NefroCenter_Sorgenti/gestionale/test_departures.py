"""Offboarding, transfer scopes and equipment custody are explicit and versioned."""
import json
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import threading

import core
import hr
import departures as dep
import document_reviews
import test_structures as fixtures


class DepartureTests(unittest.TestCase):
    tearDown = fixtures.StructureTests.tearDown
    user = fixtures.StructureTests.user

    def setUp(self):
        fixtures.StructureTests.setUp(self)
        dep.init(core); document_reviews.init(core)
        with core.connect() as c: revision = core.center(c, self.one)['revision']
        self.pid = hr.save(core, self.admin, dict(cid=self.one, revision=revision, version=0,
            name='Persona uscita', role='INF', registration='EXIT1', fields={}, custom={}))['pid']
        self.clock = patch.object(dep, '_today', return_value='2026-10-22'); self.clock.start()
        self.addCleanup(self.clock.stop)

    def case_body(self, **values):
        return dict(cid=self.one, pid=self.pid, version=0, kind='termination', effective_date='2026-10-31',
                    responsible='Responsabile Demo', reason='Cessazione pianificata', **values)

    def asset_body(self, **values):
        return dict(cid=self.one, pid=self.pid, version=0, kind='badge', inventory_code='BADGE 001',
                    label='Badge dipendente', delivery_date='2026-10-01', due_date='2026-10-31', **values)

    def create(self): return dep.case_save(core, self.manager, self.case_body())
    def assign(self): return dep.equipment_save(core, self.manager, self.asset_body())['asset']

    def task(self, case, taskid, status='done', note=''):
        return dep.task_save(core, self.hr, dict(cid=self.one, id=case['id'], version=case['version'],
            task_id=taskid, status=status, note=note))

    def close(self, case, status='completed', **values):
        return dep.case_transition(core, self.hr, dict(cid=self.one, id=case['id'], version=case['version'],
            status=status, note='Verifica conclusiva effettuata', confirm=True, **values))

    def test_completion_requires_tasks_and_returned_equipment_without_mutating_person(self):
        before = hr.read(core, self.hr, self.one, self.pid)
        asset = self.assign(); case = self.create()
        with self.assertRaises(ValueError): self.close(case)
        for task in case['tasks']: case = self.task(case, task['id'])
        self.assertFalse(case['can_complete'])
        with self.assertRaises(ValueError): self.close(case)
        dep.equipment_return(core, self.manager, dict(cid=self.one, id=asset['id'], version=1,
                                                    return_date='2026-10-22', condition='good'))
        case = dep.case_read(core, self.hr, self.one, case['id']); self.assertTrue(case['can_complete'])
        completed = self.close(case)
        self.assertEqual(completed['status'], 'completed')
        after = hr.read(core, self.hr, self.one, self.pid)
        self.assertEqual(before['person'], after['person']); self.assertEqual(before['profile'], after['profile'])
        self.assertGreaterEqual(len(completed['history']), 7)
        with self.assertRaises(ValueError): self.task(completed, 'badge')
        with self.assertRaises(ValueError):
            dep.case_save(core, self.hr, {**self.case_body(), 'id': completed['id'], 'version': completed['version']})

    def test_non_applicable_requires_reason_and_completion_requires_confirmation(self):
        case = self.create()
        with self.assertRaises(ValueError): self.task(case, 'badge', 'na')
        for task in case['tasks']: case = self.task(case, task['id'], 'na', 'Nessuna dotazione prevista')
        with self.assertRaises(ValueError):
            dep.case_transition(core, self.hr, dict(cid=self.one, id=case['id'], version=case['version'],
                status='completed', note='Controllo finale', confirm=False))
        self.assertEqual(self.close(case)['status'], 'completed')

    def test_cancellation_preserves_assignments_and_releases_active_case_constraint(self):
        asset = self.assign(); case = self.create()
        with self.assertRaises(ValueError): self.create()
        cancelled = self.close(case, 'cancelled')
        self.assertEqual(cancelled['outstanding_assets'][0]['id'], asset['id'])
        self.assertEqual(dep.overview(core, self.hr)['assets'][0]['status'], 'assigned')
        self.assertNotEqual(self.create()['id'], cancelled['id'])

    def test_scopes_roles_and_fresh_revocation(self):
        case = self.create()
        self.assertEqual([self.one], [c['id'] for c in dep.overview(core, self.manager)['centers']])
        for user in (self.operator, self.viewer):
            with self.assertRaises(PermissionError): dep.overview(core, user)
            with self.assertRaises(PermissionError): dep.case_read(core, user, self.one, case['id'])
            with self.assertRaises(PermissionError): dep.equipment_save(core, user, self.asset_body())
        with self.assertRaises(PermissionError): dep.case_read(core, self.manager, self.two, case['id'])
        with self.assertRaises(ValueError): dep.case_read(core, self.hr, self.two, case['id'])
        with core.connect() as c:
            c.execute('UPDATE users SET centers=? WHERE id=?', (core.dump([self.two]), self.manager['id'])); c.commit()
        with self.assertRaises(PermissionError): dep.case_read(core, self.manager, self.one, case['id'])
        with core.connect() as c:
            c.execute('UPDATE users SET active=0 WHERE id=?', (self.hr['id'],)); c.commit()
        with self.assertRaises(core.AuthenticationError): dep.overview(core, self.hr)

    def test_transfer_requires_both_centers_and_never_copies_person(self):
        request = {**self.case_body(), 'kind': 'transfer', 'destination_cid': self.two}
        with self.assertRaises(PermissionError): dep.case_save(core, self.manager, request)
        with self.assertRaises(ValueError): dep.case_save(core, self.hr, {**request, 'destination_cid': self.one})
        case = dep.case_save(core, self.hr, request)
        self.assertEqual(case['destination_cid'], self.two)
        with core.connect() as c: self.assertEqual(core.objects(c, 'people', self.two), [])

    def test_equipment_code_uniqueness_return_conditions_and_reassignment(self):
        asset = self.assign()
        with self.assertRaises(ValueError): dep.equipment_save(core, self.hr, {**self.asset_body(), 'inventory_code':' badge   001 '})
        for day, condition, note in [('2026-09-30', 'good', ''), ('2026-10-23', 'good', ''),
                                      ('2026-10-22', 'damaged', ''), ('2026-10-22', 'invalid', '')]:
            with self.subTest(day=day, condition=condition), self.assertRaises(ValueError):
                dep.equipment_return(core, self.hr, dict(cid=self.one, id=asset['id'], version=1,
                    return_date=day, condition=condition, note=note))
        returned = dep.equipment_return(core, self.hr, dict(cid=self.one, id=asset['id'], version=1,
            return_date='2026-10-22', condition='damaged', note='Supporto plastica lesionato'))['asset']
        self.assertEqual(returned['status'], 'returned')
        with self.assertRaises(ValueError):
            dep.equipment_save(core, self.hr, {**self.asset_body(), 'id':asset['id'], 'version':2})
        self.assertNotEqual(self.assign()['id'], asset['id'])

    def test_malformed_inputs_stale_versions_and_future_deliveries(self):
        for method in (dep.case_save, dep.task_save, dep.case_transition, dep.equipment_save, dep.equipment_return):
            for invalid in (None, [], 'text'):
                with self.subTest(method=method.__name__, invalid=invalid), self.assertRaises(ValueError): method(core,self.hr,invalid)
        for bad in ({'kind': []}, {'effective_date': '2026-02-30'}, {'reason': 'short'}, {'version': True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): dep.case_save(core,self.hr,{**self.case_body(),**bad})
        for bad in ({'kind': {}}, {'delivery_date':'2026-10-23'}, {'due_date':'2026-09-01'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): dep.equipment_save(core,self.hr,{**self.asset_body(),**bad})
        case=self.create(); self.task(case,'badge')
        with self.assertRaises(ValueError): self.task(case,'keys')
        for cid, oid in (([], case['id']), (self.one, [])):
            with self.assertRaises(ValueError): dep.case_read(core,self.hr,cid,oid)

    def test_simultaneous_assignment_cannot_double_issue_same_inventory_code(self):
        ready=threading.Barrier(2)
        def assign(_):
            ready.wait(timeout=5)
            try:return self.assign()
            except ValueError:return None
        with ThreadPoolExecutor(max_workers=2) as workers: results=list(workers.map(assign,range(2)))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(len(dep.overview(core,self.hr)['assets']),1)


if __name__=='__main__':unittest.main()
