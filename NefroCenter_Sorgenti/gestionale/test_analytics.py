"""Independent fixtures for aggregation, denominators and tenant boundaries."""
import copy
import json
import unittest
from datetime import date
import analytics
import core
import hr
import test_core


class StatisticsFixture(unittest.TestCase):
    req = test_core.AccessTests.req

    def setUp(self):
        test_core.AccessTests.setUp(self)
        self.seq = 0
        # The same local id in two centers must remain two separate identities.
        with core.connect() as c:
            p = core.objects(c, 'people', self.a)[0]
            core.put(c, 'people', self.b, {**p, 'name':'Seconda persona', 'role':'MED', 'registration':'B001'})
            c.commit()

    tearDown = test_core.AccessTests.tearDown

    def entry(self, cid=None, **fields):
        self.seq += 1
        item = dict(id='stat-'+str(self.seq), person_id=self.person, day='2026-10-04', slot='m',
                    code='m', code_label='Mattina', layer='actual', kind='work', start='07:00',
                    end='13:00', overnight=False, pause=0, holiday=False, work_site='Centro A',
                    credit_minutes=0, note='')
        item.update(fields)
        with core.connect() as c:
            core.put(c, 'entries', cid or self.a, item); c.commit()
        return item

    def report(self, **filters):
        return analytics.report(core, self.admin, '2026-10', '2026-12', **filters)


class AnalyticsTests(StatisticsFixture):
    def test_known_hours_overnight_and_missing_are_not_zero(self):
        self.entry(start='22:00', end='04:00', overnight=True, pause=60)
        self.entry(day='2026-11-04', start='', end='')
        data = self.report()
        self.assertEqual((data['summary']['minutes'], data['summary']['work_shifts'], data['summary']['hours_completeness']), (300, 2, 50))
        self.assertEqual([r['minutes'] for r in data['monthly']], [300, None, None])
        self.assertEqual(data['summary']['missing_hours'], 1)

    def test_distinct_days_centers_and_weighted_rates(self):
        for day in ['04','05','06']:self.entry(day='2026-10-'+day)
        self.entry(self.b, start='', end='', work_site='Centro B')
        for slot in ['m','p']:self.entry(day='2026-10-08',slot=slot, kind='absence', code='F', code_label='Ferie', start='', end='')
        self.entry(self.b, day='2026-10-08',slot='p', kind='absence', code='F', code_label='Ferie', start='', end='', work_site='Centro B')
        data = self.report(); summary = data['summary']
        self.assertEqual((summary['work_shifts'], summary['hours_completeness']), (4,75))
        self.assertEqual((summary['absence_slots'], summary['absence_days'], summary['people_count']), (3,2,2))
        self.assertEqual(summary['absence_share'],42.9)
        self.assertEqual(len(data['by_person']),2)

    def test_plan_can_be_resolved_by_absence_and_rest_is_not_absence(self):
        self.entry(layer='planned')
        self.entry(day='2026-10-05',layer='planned')
        self.entry(kind='absence',code='F',code_label='Ferie',start='',end='')
        self.entry(day='2026-10-06',kind='rest',code='R',start='',end='')
        s=self.report()['summary']
        self.assertEqual((s['planned_work'],s['pending_work'],s['absence_slots'],s['rest_slots']),(2,1,1,1))
        self.assertEqual((s['minutes'],s['hours_completeness'],s['absence_share']),(0,None,100))

    def test_custom_causes_keep_different_meanings_separate(self):
        self.entry(kind='absence',code='X',code_label='Formazione',start='',end='')
        self.entry(self.b,kind='absence',code='X',code_label='Permesso',start='',end='')
        self.assertEqual({r['label'] for r in self.report()['by_cause']},{'Formazione','Permesso'})

    def test_filters_apply_to_every_breakdown_and_csv(self):
        self.entry();self.entry(self.b,work_site='Centro B')
        data=self.report(role='INF')
        self.assertEqual(data['summary']['minutes'],360)
        self.assertEqual(sum(r['known_minutes'] for r in data['monthly']),360)
        self.assertEqual(sum(r['known_minutes'] for r in data['by_center']),360)
        self.assertEqual(len(data['by_person']),1)
        self.assertEqual(data['by_role'][0]['role'],'INF')
        csv=analytics.export_csv(core,self.admin,'2026-10','2026-10',self.a,'INF',self.person).decode('utf-8-sig')
        self.assertIn(';360;1;0;',csv);self.assertNotIn('Centro B',csv)

    def test_scope_permissions_current_revocation_and_private_summary(self):
        self.entry();self.entry(self.b)
        data=analytics.report(core,self.viewer,'2026-10','2026-10')
        self.assertEqual([c['id'] for c in data['centers']],[self.a]);self.assertIsNone(data['hr'])
        with self.assertRaises(PermissionError):analytics.report(core,self.operator,'2026-10','2026-10',self.b)
        cfg=core.snapshot(self.admin,self.a,'2026-10')['center']['config'];cfg['operator_export']=False
        core.mutate(self.admin,'center_save',{**self.req(),'config':cfg})
        self.assertFalse(analytics.report(core,self.operator,'2026-10','2026-10')['export_allowed'])
        with self.assertRaises(PermissionError):analytics.export_csv(core,self.operator,'2026-10','2026-10')

    def test_empty_period_and_boundaries(self):
        data=self.report();self.assertIsNone(data['summary']['minutes']);self.assertFalse(data['has_records'])
        self.assertEqual(data['quality']['empty_months'],6)
        self.assertEqual(len(analytics.months_between('2025-01','2026-12')),24)
        for first,last in [('2025-01','2027-01'),('2026-12','2026-01'),('2026-13','2026-13'),('2026-1','2026-02')]:
            with self.subTest(first=first,last=last),self.assertRaises(ValueError):analytics.months_between(first,last)
        with self.assertRaises(ValueError):self.report(person_id=self.person)
        with self.assertRaises(ValueError):self.report(cid=self.a,person_id='missing')

    def test_hr_is_current_scoped_and_does_not_count_completed_tasks(self):
        with core.connect() as c:
            profile=hr.profile(c,self.a,self.person)
            profile.update(stage='active',fields={'identity_expiry':'2026-10-20'},tasks=[
                {'status':'todo','due':'2026-10-01'},{'status':'doing','due':'2026-10-22'},
                {'status':'done','due':'2026-10-01'},{'status':'na','due':'2026-10-01'}])
            c.execute('INSERT INTO hr_profiles VALUES (?,?,?,?)',(self.a,self.person,1,json.dumps(profile)));c.commit()
        data=analytics.report(core,self.admin,'2025-01','2025-01',today=date(2026,10,17))
        h=data['hr'];self.assertEqual((h['active_people'],h['missing_profiles'],h['onboarding_open']),(2,1,1))
        self.assertEqual((h['tasks_open'],h['tasks_overdue'],h['deadlines_next30'],h['deadlines_overdue']),(2,1,2,1))
        with core.connect() as c:
            p=core.objects(c,'people',self.a)[0];core.put(c,'people',self.a,{**p,'active':False});c.commit()
        self.assertEqual(self.report(cid=self.a)['hr']['active_people'],0)

    def test_orphan_records_surface_a_quality_failure_and_do_not_enter_totals(self):
        self.entry(person_id='deleted');self.entry()
        data=self.report();self.assertEqual(data['quality']['unmatched_records'],1)
        self.assertEqual(data['summary']['work_shifts'],1)


if __name__=='__main__':unittest.main(verbosity=2)
