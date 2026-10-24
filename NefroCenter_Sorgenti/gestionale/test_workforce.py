"""Identity and dated agreements: scope, concurrency and frozen monthly totals."""
import copy
import sqlite3
import unittest

import agreements
import core
import workforce
from test_analytics import StatisticsFixture
from test_core import PASSWORD


class WorkforceTests(StatisticsFixture):
    def setUp(self):
        super().setUp()
        workforce.init(core)
        self.manager = self.user('responsabile', 'manager', [self.a])
        self.hr = self.user('ufficiohr', 'hr', [])

    def user(self, name, role, centers):
        core.mutate(self.admin, 'user_save', {'user':dict(username=name, name=name,
            role=role, centers=centers, active=True, password=PASSWORD)})
        with core.connect() as c:
            return core.public_user(c.execute('SELECT * FROM users WHERE username=?', (name,)).fetchone())

    def assignment(self, cid=None):
        with core.connect() as c:
            return workforce._assignment(c, cid or self.a, self.person)

    def request(self, cid=None, **values):
        a = self.assignment(cid)
        return dict(cid=a['cid'], pid=a['pid'], assignment_version=a['version'],
                    reason='Verifica documentale HR', **values)

    def contract(self, start, end='', cid=None, **data):
        return workforce.mutate(core, self.hr, 'workforce_contract', self.request(cid,
            effective_from=start, effective_to=end,
            data=dict(role='INF', contract_type='Indeterminato', ccnl='Sanità', level='D',
                      weekly_hours=36, part_time_percent=100, **data)))['record']

    def economic(self, start='2026-10-01', end='', **overrides):
        with core.connect() as c:
            proposal=agreements.proposal(core.center(c,self.a)['config'], {})
        proposal.update(confirmed=True,basis='all',fixed_deduction=0,weekday_rate=50,holiday_rate=80)
        proposal.update(overrides)
        return workforce.mutate(core, self.hr, 'workforce_economic', self.request(
            effective_from=start,effective_to=end,data=proposal))['record']

    def apply(self):
        preview=workforce.preview(core,self.hr,self.a,self.person,'2026-10')
        return workforce.mutate(core,self.hr,'workforce_apply',self.request(
            month='2026-10',revision=preview['revision']))

    def test_initial_identity_is_distinct_and_migration_idempotent(self):
        # Equal local IDs and even equal names/registration never imply same person.
        with core.connect() as c:
            p=core.objects(c,'people',self.a)[0]
            core.put(c,'people',self.b,p)
            c.commit()
        first=self.assignment();second=self.assignment(self.b)
        self.assertNotEqual(first['global_id'],second['global_id'])
        workforce.init(core)
        self.assertEqual(first,self.assignment())
        self.assertEqual(second,self.assignment(self.b))

    def test_upgrade_preserves_pre_migration_snapshot_and_existing_people(self):
        with core.connect() as c:
            before=[tuple(r) for r in c.execute('SELECT cid,id,data FROM people ORDER BY cid,id')]
            for table in ('workforce_history','workforce_economics','workforce_contracts',
                          'workforce_assignments','group_people','payroll_templates'):
                c.execute('DROP TABLE '+table)
            c.execute('PRAGMA user_version=5');c.commit()
        existing=set((core.DB.parent/'backups').iterdir())
        core.init_db()
        new=set((core.DB.parent/'backups').iterdir())-existing
        self.assertEqual(len(new),1)
        with sqlite3.connect(next(iter(new))) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],5)
            self.assertEqual(c.execute('SELECT cid,id,data FROM people ORDER BY cid,id').fetchall(),before)
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='workforce_assignments'").fetchone())
        with core.connect() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],8)
            self.assertEqual([tuple(r) for r in c.execute('SELECT cid,id,data FROM people ORDER BY cid,id')],before)
            self.assertEqual(c.execute('SELECT count(*) FROM workforce_assignments').fetchone()[0],2)
        core.init_db()
        self.assertEqual(set((core.DB.parent/'backups').iterdir()),existing|new)

    def test_link_is_explicit_audited_scoped_and_optimistic(self):
        target=self.assignment(self.b)['global_id']
        body=self.request(global_id=target,target_version=1)
        with self.assertRaises(PermissionError):
            workforce.mutate(core,self.manager,'workforce_link',body)
        workforce.mutate(core,self.hr,'workforce_link',body)
        self.assertEqual(self.assignment()['global_id'],target)
        self.assertEqual(len(workforce.read(core,self.hr,target)['groups'][0]['assignments']),2)
        manager=workforce.read(core,self.manager,target)['groups'][0]['assignments']
        self.assertEqual([a['cid'] for a in manager],[self.a])
        with self.assertRaises(ValueError):
            workforce.mutate(core,self.hr,'workforce_link',body)
        with self.assertRaises(PermissionError):
            workforce.mutate(core,self.manager,'workforce_link',self.request(global_id=''))
        workforce.mutate(core,self.hr,'workforce_link',self.request(global_id=''))
        self.assertNotEqual(self.assignment()['global_id'],target)
        with core.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM workforce_history').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT count(*) FROM people').fetchone()[0],2)

    def test_target_version_and_duplicate_assignment_in_center_rejected(self):
        target=self.assignment(self.b)['global_id']
        with self.assertRaisesRegex(ValueError,'destinazione modificata'):
            workforce.mutate(core,self.hr,'workforce_link',self.request(global_id=target,target_version=99))
        own=self.assignment()['global_id']
        with self.assertRaisesRegex(ValueError,'questo centro'):
            workforce.mutate(core,self.hr,'workforce_link',self.request(global_id=own,target_version=1))

    def test_cross_center_overlap_uses_linked_identity_not_coincident_registration(self):
        with core.connect() as c:
            person=core.objects(c,'people',self.b)[0]
            core.put(c,'people',self.b,{**person,'registration':'M001'})
            c.commit()
        def shift(cid,day):
            return core.mutate(self.admin,'entry',{**self.req(cid),'entry':dict(
                person_id=self.person,day=day,slot='m',code='m',layer='actual')})
        shift(self.b,'2026-10-14')
        shift(self.a,'2026-10-14')  # Two independent identities with a local code in common.
        target=self.assignment(self.b)['global_id']
        workforce.mutate(core,self.hr,'workforce_link',self.request(global_id=target,target_version=1))
        shift(self.b,'2026-10-15')
        with self.assertRaises(ValueError):
            shift(self.a,'2026-10-15')

    def test_read_and_write_refresh_permissions(self):
        for user in (self.operator,self.viewer):
            with self.assertRaises(PermissionError):workforce.read(core,user)
            with self.assertRaises(PermissionError):workforce.preview(core,user,self.a,self.person,'2026-10')
        with self.assertRaises(PermissionError):
            workforce.preview(core,self.manager,self.b,self.person,'2026-10')
        with core.connect() as c:
            c.execute('UPDATE users SET role=? WHERE id=?',('viewer',self.hr['id']));c.commit()
        with self.assertRaises(PermissionError):workforce.read(core,self.hr)

    def test_contract_dates_are_inclusive_nonoverlapping_and_do_not_overwrite_person(self):
        first=self.contract('2026-10-01','2026-10-15')
        with self.assertRaisesRegex(ValueError,'sovrapposti'):
            self.contract('2026-10-15','2026-10-31')
        data={**first['data'],'role':'MED','weekly_hours':18,'part_time_percent':50}
        workforce.mutate(core,self.hr,'workforce_contract',self.request(
            effective_from='2026-10-16',effective_to='',data=data))
        with core.connect() as c:
            self.assertIsNone(workforce.effective_person(c,self.a,self.person,'2026-09-30')['effective_contract'])
            old=workforce.effective_person(c,self.a,self.person,'2026-10-15')
            new=workforce.effective_person(c,self.a,self.person,'2026-10-16')
            self.assertEqual((old['role'],old['weekly_hours']),('INF',36))
            self.assertEqual((new['role'],new['weekly_hours'],new['part_time_percent']),('MED',18,50))
            self.assertEqual(core.objects(c,'people',self.a)[0]['role'],'INF')
        with self.assertRaisesRegex(ValueError,'Decorrenza modificata'):
            workforce.mutate(core,self.hr,'workforce_contract',self.request(id=first['id'],version=0,
                effective_from=first['effective_from'],effective_to=first['effective_to'],data=first['data']))

    def test_invalid_numeric_contract_or_reversed_interval_has_no_side_effects(self):
        for field,value in [('weekly_hours',float('nan')),('weekly_hours',True),('part_time_percent',101)]:
            data=dict(role='INF',contract_type='',weekly_hours=36,part_time_percent=100)
            data[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                workforce.mutate(core,self.hr,'workforce_contract',self.request(
                    effective_from='2026-10-01',data=data))
        with self.assertRaises(ValueError):self.contract('2026-11-01','2026-10-31')
        self.assertEqual(self.assignment()['version'],1)

    def test_intramonth_economics_and_frozen_month_survive_history_correction(self):
        first=self.economic(end='2026-10-15',weekday_rate=50)
        self.economic(start='2026-10-16',weekday_rate=70)
        self.entry(day='2026-10-05');self.entry(day='2026-10-20')
        preview=workforce.preview(core,self.hr,self.a,self.person,'2026-10')
        self.assertFalse(preview['manual_required'])
        self.assertEqual((preview['result']['amount'],preview['result']['shifts']),(120,2))
        self.apply()
        frozen=copy.deepcopy(core.snapshot(self.admin,self.a,'2026-10')['period']['agreements'][self.person])
        workforce.mutate(core,self.hr,'workforce_economic',self.request(id=first['id'],version=1,
            effective_from=first['effective_from'],effective_to=first['effective_to'],
            data={**first['data'],'weekday_rate':99}))
        snap=core.snapshot(self.admin,self.a,'2026-10')
        self.assertEqual(snap['period']['agreements'][self.person],frozen)
        self.assertEqual(agreements.report(core,self.admin,self.a,'2026-10')['rows'][0]['amount'],120)
        self.assertEqual(workforce.preview(core,self.hr,self.a,self.person,'2026-10')['result']['amount'],169)

    def test_missing_hours_remain_blocking_and_fixed_intramonth_requires_manual(self):
        self.economic(end='2026-10-15',model='hours',weekday_rate=10)
        second=self.economic(start='2026-10-16',model='hours',weekday_rate=12)
        self.entry(day='2026-10-05');self.entry(day='2026-10-20',start='',end='')
        preview=workforce.preview(core,self.hr,self.a,self.person,'2026-10')
        self.assertEqual(preview['result']['status'],'orari_mancanti')
        self.assertIsNone(preview['result']['amount'])
        workforce.mutate(core,self.hr,'workforce_economic',self.request(id=second['id'],version=1,
            effective_from=second['effective_from'],effective_to=second['effective_to'],
            data={**second['data'],'fixed_amount':100}))
        self.assertTrue(workforce.preview(core,self.hr,self.a,self.person,'2026-10')['manual_required'])
        with self.assertRaisesRegex(ValueError,'pro-rata'):self.apply()

    def test_gaps_unconfirmed_stale_preview_and_closed_month_block_application(self):
        self.entry()
        record=self.economic(start='2026-10-02',confirmed=False)
        self.assertTrue(workforce.preview(core,self.hr,self.a,self.person,'2026-10')['manual_required'])
        workforce.mutate(core,self.hr,'workforce_economic',self.request(id=record['id'],version=1,
            effective_from='2026-10-01',effective_to='',data=record['data']))
        with self.assertRaisesRegex(ValueError,'Confermare'):self.apply()
        workforce.mutate(core,self.hr,'workforce_economic',self.request(id=record['id'],version=2,
            effective_from='2026-10-01',effective_to='',data={**record['data'],'confirmed':True}))
        preview=workforce.preview(core,self.hr,self.a,self.person,'2026-10')
        with self.assertRaisesRegex(ValueError,'centro cambiati'):
            workforce.mutate(core,self.hr,'workforce_apply',self.request(month='2026-10',revision=preview['revision']-1))
        self.apply()
        core.mutate(self.admin,'period_verify',{**self.req(),'verified':True})
        core.mutate(self.admin,'close',self.req())
        with self.assertRaisesRegex(ValueError,'Mese chiuso'):self.apply()


if __name__ == '__main__':unittest.main()
