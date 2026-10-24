"""Operational tasks are actionable, read-only and scoped to current permissions."""
import json
import unittest
from datetime import date
from unittest.mock import patch

import core
import hr
import tasks
from test_analytics import StatisticsFixture


class TaskTests(StatisticsFixture):
    def report(self,user=None,**options):
        return tasks.report(core,user or self.admin,'2026-10',today=date(2026,11,1),**options)

    def test_pending_plan_missing_hours_calendar_and_closure_are_distinct(self):
        self.entry(layer='planned')
        self.entry(kind='absence',code='F',code_label='Ferie',start='',end='')
        self.entry(day='2026-10-05',layer='planned')
        self.entry(day='2026-10-06',start='',end='')
        before=core.snapshot(self.admin,self.a,'2026-10')
        result=self.report(cid=self.a)
        self.assertEqual(result['counts']['consuntivi'],1)
        self.assertEqual(result['counts']['orari'],1)
        self.assertEqual(result['counts']['calendario'],1)
        self.assertEqual(result['counts']['chiusure'],1)
        self.assertEqual(core.snapshot(self.admin,self.a,'2026-10'),before)
        pending=next(i for i in result['items'] if i['category']=='consuntivi')
        self.assertEqual((pending['cid'],pending['pid'],pending['day']),(self.a,self.person,'2026-10-05'))

    def test_future_plan_does_not_become_pending_until_due(self):
        self.entry(day='2026-10-25',layer='planned')
        report=tasks.report(core,self.admin,'2026-10',today=date(2026,10,18))
        self.assertNotIn('consuntivi',report['counts'])
        self.assertNotIn('chiusure',report['counts'])

    def test_hr_tasks_and_private_details_are_absent_for_operator_and_viewer(self):
        with core.connect() as c:
            profile=hr.profile(c,self.a,self.person)
            profile.update(stage='active',fields={'identity_expiry':'2026-10-01'},tasks=[
                dict(status='todo',due='2026-10-05',label='Documento privato HR'),
                dict(status='done',due='2026-10-01',label='Attività completata')])
            c.execute('INSERT INTO hr_profiles VALUES(?,?,?,?)',(self.a,self.person,1,json.dumps(profile)));c.commit()
        result=self.report()
        self.assertEqual(result['counts']['onboarding'],1)
        self.assertEqual(result['counts']['fascicoli'],1)
        self.assertTrue(any(i['priority']=='urgent' and i['category']=='scadenze' for i in result['items']))
        self.assertNotIn('Attività completata',json.dumps(result))
        for user in (self.operator,self.viewer):
            visible=self.report(user)
            self.assertFalse(visible['hr_visible'])
            self.assertEqual({c['id'] for c in visible['centers']},{self.a})
            self.assertFalse({'scadenze','fascicoli','onboarding'} & set(visible['counts']))
            self.assertNotIn('Documento privato HR',json.dumps(visible))
            with self.assertRaises(PermissionError):self.report(user,cid=self.b)

    def test_revoked_scope_is_refreshed_and_inactive_profiles_excluded(self):
        with core.connect() as c:
            person=core.objects(c,'people',self.a)[0]
            core.put(c,'people',self.a,{**person,'active':False})
            c.execute('UPDATE users SET centers=? WHERE id=?',(core.dump([self.b]),self.viewer['id']));c.commit()
        self.assertNotIn('fascicoli',self.report(cid=self.a)['counts'])
        self.assertEqual({c['id'] for c in self.report(self.viewer)['centers']},{self.b})
        with self.assertRaises(PermissionError):self.report(self.viewer,cid=self.a)

    def test_admin_backup_error_is_actionable_and_not_exposed_to_other_roles(self):
        with patch('backup_policy.status',return_value={'last_error':'NAS /rete/riservata non disponibile'}):
            result=self.report()
            issue=next(i for i in result['items'] if i['category']=='backup')
            self.assertEqual((issue['priority'],issue['section']),('urgent','esportazioni'))
            self.assertNotIn('/rete/riservata',json.dumps(self.report(self.viewer)))


if __name__ == '__main__':unittest.main()
