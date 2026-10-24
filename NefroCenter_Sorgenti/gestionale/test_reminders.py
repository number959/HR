"""Scheduled summaries: scope, approvals, durable deduplication and mocked SMTP."""
import copy
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import communications as mail
import core
import reminders
import test_communications as fixtures


class ReminderTests(unittest.TestCase):
    setUpBase = fixtures.CommunicationTests.setUp
    tearDown = fixtures.CommunicationTests.tearDown
    person = fixtures.CommunicationTests.person
    config = fixtures.CommunicationTests.config

    def setUp(self):
        self.setUpBase(); reminders.init(core)
        self.now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
        for cid, pid in ((self.a, 'p1'), (self.b, 'p2')):
            with core.connect() as c:
                row=c.execute('SELECT data FROM hr_profiles WHERE cid=? AND pid=?',(cid,pid)).fetchone()
                data=json.loads(row['data']);data['fields']['end_date']='2026-10-29'
                c.execute('UPDATE hr_profiles SET data=? WHERE cid=? AND pid=?',(core.dump(data),cid,pid));c.commit()

    def payload(self, **extra):
        with core.connect() as c:
            settings=reminders._settings(c)
        return {k:copy.deepcopy(settings[k]) for k in ['version',*reminders.DEFAULTS]} | extra

    def enable(self, **extra):
        self.config()
        body=self.payload(enabled=True, **extra)
        view=reminders.preview(core,self.admin,body,self.now)
        return reminders.configure(core,self.admin,{**body,'confirmed':True,'fingerprint':view['fingerprint']},self.now)

    def test_defaults_preview_never_sends_and_permissions_are_fresh(self):
        with patch.object(mail,'_send_one') as send:
            self.assertEqual(reminders.run(core,self.now)['state'],'disabled')
            p=reminders.preview(core,self.hr,now=self.now)
            self.assertEqual(p['total_messages'],2)
            self.assertTrue(all('Persona p' not in m['body'] for m in p['messages']))
            self.assertFalse(reminders.overview(core,self.admin,self.now)['config']['enabled'])
            send.assert_not_called()
        for role in ('manager','operator','viewer'):
            with self.assertRaises(PermissionError):reminders.overview(core,self.users[role],self.now)
            with self.assertRaises(PermissionError):reminders.preview(core,self.users[role],now=self.now)
        with self.assertRaises(PermissionError):reminders.configure(core,self.hr,self.payload(),self.now)
        with core.connect() as c:
            c.execute("UPDATE users SET role='viewer' WHERE id='hr'");c.commit()
        with self.assertRaises(PermissionError):reminders.overview(core,self.hr,self.now)

    def test_explicit_preview_confirmation_and_smtp_are_required(self):
        body=self.payload(enabled=True)
        with self.assertRaisesRegex(ValueError,'anteprima'):reminders.configure(core,self.admin,body,self.now)
        p=reminders.preview(core,self.admin,body,self.now)
        with self.assertRaisesRegex(ValueError,'SMTP'):reminders.configure(core,self.admin,{**body,'confirmed':True,'fingerprint':p['fingerprint']},self.now)
        self.config();p=reminders.preview(core,self.admin,body,self.now)
        with core.connect() as c:
            c.execute('UPDATE structure_profiles SET data=? WHERE cid=?',(core.dump({'hr_email':'new@example.org'}),self.a));c.commit()
        with self.assertRaisesRegex(ValueError,'anteprima'):reminders.configure(core,self.admin,{**body,'confirmed':True,'fingerprint':p['fingerprint']},self.now)
        body=self.payload(enabled=False);reminders.configure(core,self.admin,body,self.now)
        with self.assertRaisesRegex(ValueError,'cambiata'):reminders.configure(core,self.admin,body,self.now)

    def test_missing_routes_invalid_config_and_legacy_inputs(self):
        self.config()
        with core.connect() as c:
            c.execute('UPDATE structure_profiles SET data=? WHERE cid=?',(core.dump({}),self.a));c.commit()
        body=self.payload(enabled=True);p=reminders.preview(core,self.admin,body,self.now)
        self.assertFalse(p['can_enable'])
        with self.assertRaisesRegex(ValueError,'recapiti'):reminders.configure(core,self.admin,{**body,'confirmed':True,'fingerprint':p['fingerprint']},self.now)
        for changes in ({'offsets':[]},{'offsets':[True]},{'hour':24},{'hour':True},{'centers':['unknown']},{'topics':[]},{'recipient_mode':'other'},{'recipient_mode':'central_hr','central_hr_email':''},{'central_hr_email':'one@example.org\nBcc: bad@example.org'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):reminders.preview(core,self.admin,self.payload(**changes),self.now)
        with self.assertRaises(ValueError):reminders.configure(core,self.admin,[],self.now)

    def test_offsets_catch_up_once_per_event_and_send_only_summaries(self):
        self.enable()
        with patch.object(mail,'_send_one',return_value=('accepted','')) as send:
            first=reminders.run(core,self.now);second=reminders.run(core,self.now)
            self.assertEqual(first['messages'],2);self.assertEqual(second['state'],'no_work');self.assertEqual(send.call_count,2)
            for call in send.call_args_list:
                message=call.args[1]
                self.assertNotIn('Persona p',message['body'])
                self.assertNotIn('p1',message['body']);self.assertNotIn('p2',message['body'])
                self.assertIn('Contratti e periodo di prova: 1',message['body'])
            tomorrow=reminders.run(core,self.now+timedelta(days=1));self.assertEqual(tomorrow['messages'],0)
            due=reminders.run(core,self.now+timedelta(days=7));self.assertEqual(due['messages'],2)
            after=reminders.run(core,self.now+timedelta(days=8));self.assertEqual(after['messages'],0)
        self.assertEqual(len(reminders.overview(core,self.hr,self.now)['history']),4)

    def test_failed_uncertain_are_never_retried_and_manual_send_rejected(self):
        self.enable()
        with patch.object(mail,'_send_one',side_effect=[('failed','Connection refused'),('uncertain','Result unknown')]) as send:
            run=reminders.run(core,self.now)
            self.assertEqual(reminders.run(core,self.now)['messages'],0)
            campaign=mail.campaign(core,self.hr,run['campaign_id'])
            self.assertFalse(campaign['can_send']);self.assertFalse(campaign['can_retry_failed'])
            for retry in (False,True):
                with self.assertRaisesRegex(ValueError,'promemoria automatici'):mail.send_campaign(core,self.hr,{'id':run['campaign_id'],'confirm':True,'confirmation_token':campaign['confirmation_token'],'retry_failed':retry})
            self.assertEqual(send.call_count,2)

    def test_simultaneous_workers_deduplicate_claims(self):
        self.enable()
        with patch.object(mail,'_send_one',return_value=('accepted','')) as send:
            with ThreadPoolExecutor(max_workers=2) as pool:
                result=list(pool.map(lambda _:reminders.run(core,self.now),range(2)))
            self.assertEqual(sum(r['messages'] for r in result),2);self.assertEqual(send.call_count,2)
        with core.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM reminder_events').fetchone()[0],2)

    def test_clock_daily_budget_and_shared_hourly_limit(self):
        self.enable(max_daily_messages=1,hour=8)
        with patch.object(mail,'_send_one',return_value=('accepted','')) as send:
            self.assertEqual(reminders.run(core,self.now.replace(hour=4))['state'],'waiting')
            self.assertEqual(reminders.run(core,self.now)['messages'],1)
            self.assertEqual(reminders.run(core,self.now)['state'],'rate_limited')
            self.assertEqual(reminders.run(core,self.now+timedelta(days=1))['messages'],1)
            self.assertEqual(send.call_count,2)
        cfg=self.config(max_per_hour=1)
        with core.connect() as c:
            c.execute('UPDATE communication_attempts SET started_epoch=?',(self.now.timestamp(),));c.commit()
        with patch.object(mail,'_send_one') as send:
            self.assertEqual(reminders.run(core,self.now)['state'],'rate_limited');send.assert_not_called()

    def test_changed_recipient_requires_new_approval_and_revoked_admin_stops_worker(self):
        self.enable()
        with core.connect() as c:
            c.execute('UPDATE structure_profiles SET data=? WHERE cid=?',(core.dump({'hr_email':'new@example.org'}),self.a));c.commit()
        view=reminders.overview(core,self.hr,self.now);self.assertEqual(view['changed_routes'],[self.a])
        with patch.object(mail,'_send_one',return_value=('accepted','')) as send:
            self.assertEqual(reminders.run(core,self.now)['messages'],1)
            self.assertEqual(send.call_args.args[1]['cid'],self.b)
        with core.connect() as c:
            c.execute("UPDATE users SET active=0 WHERE id='admin'");c.commit()
        with patch.object(mail,'_send_one') as send:
            self.assertEqual(reminders.run(core,self.now)['state'],'authorization_changed');send.assert_not_called()

    def test_disabled_or_restore_during_batch_cancels_remaining_sends(self):
        self.enable()
        def restore(config,recipient,message_id):
            with core.connect() as c:
                c.execute('BEGIN IMMEDIATE');reminders.after_restore(core,c);c.commit()
            return 'accepted',''
        with patch.object(mail,'_send_one',side_effect=restore) as send:
            run=reminders.run(core,self.now);self.assertEqual(send.call_count,1)
        state=reminders.overview(core,self.admin,self.now)
        self.assertFalse(state['config']['enabled']);self.assertTrue(all(h['status']=='uncertain' for h in state['history']))
        with patch.object(mail,'_send_one') as send:
            self.assertEqual(reminders.run(core,self.now)['state'],'disabled');send.assert_not_called()

    def test_configuration_revoked_between_messages_stops_batch(self):
        self.enable()
        def revoke(config,recipient,message_id):
            with core.connect() as c:
                c.execute("UPDATE users SET active=0 WHERE id='admin'");c.commit()
            return 'accepted',''
        with patch.object(mail,'_send_one',side_effect=revoke) as send:
            reminders.run(core,self.now);self.assertEqual(send.call_count,1)
        with core.connect() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT status FROM communication_recipients ORDER BY ordinal')],['accepted','failed'])

    def test_all_sources_finished_tasks_inactive_people_and_old_deadlines(self):
        with core.connect() as c:
            row=c.execute('SELECT data FROM hr_profiles WHERE cid=? AND pid=?',(self.a,'p1')).fetchone()
            data=json.loads(row['data']);data['fields'].update(probation_end='2026-10-27',identity_expiry='2026-10-28',registration_expiry='2026-10-29',work_permit_expiry='2026-01-01')
            data['tasks']=[{'id':'open','status':'todo','due':'2026-10-21'}, {'id':'done','status':'done','due':'2026-10-21'}, {'id':'future','status':'todo','due':'2026-10-23'}]
            c.execute('UPDATE hr_profiles SET data=? WHERE cid=? AND pid=?',(core.dump(data),self.a,'p1'))
            c.execute('INSERT INTO hr_documents VALUES(?,?,?,?,?,?,?,?,?,?)',('document-one',self.a,'p1','scan.pdf','other','2026-10-29',core.now(),'admin','digest',b'fixture'))
            core.put(c,'entries',self.a,{'id':'previous','pid':'p1','day':'2026-09-10','slot':'M','kind':'actual','code':'L'})
            c.commit()
        p=reminders.preview(core,self.hr,self.payload(centers=[self.a]),self.now)
        self.assertEqual({e['topic'] for e in p['candidates']},set(reminders.TOPICS))
        keys={e['source_key'] for e in p['candidates']}
        self.assertIn('onboarding:p1:open',keys);self.assertNotIn('onboarding:p1:done',keys);self.assertNotIn('onboarding:p1:future',keys)
        self.assertNotIn('profile:p1:work_permit_expiry',keys)
        with core.connect() as c:
            c.execute('INSERT INTO periods VALUES(?,?,?)',(self.a,'2026-09',core.dump({'verified':True})))
            person=core.objects(c,'people',self.a)[0];person['active']=False;core.put(c,'people',self.a,person);c.commit()
        self.assertEqual(reminders.preview(core,self.hr,self.payload(centers=[self.a]),self.now)['total_events'],0)

    def test_central_routes_deduplicate_same_address_within_structure(self):
        body=self.payload(recipient_mode='both',central_hr_email='CENTER-A@example.com',centers=[self.a])
        p=reminders.preview(core,self.admin,body,self.now)
        self.assertEqual(p['routes'],{self.a:['center-a@example.com']});self.assertEqual(p['total_messages'],1)
        p=reminders.preview(core,self.admin,self.payload(recipient_mode='central_hr',central_hr_email='central@example.org'),self.now)
        self.assertEqual(p['total_messages'],2)
        self.assertEqual({m['email'] for m in p['messages']},{'central@example.org'})

    def test_stale_claim_is_uncertain_without_new_delivery(self):
        self.enable()
        with patch.object(mail,'_send_one',return_value=('accepted','')) as send:reminders.run(core,self.now)
        with core.connect() as c:
            c.execute("UPDATE communication_recipients SET status='sending',claimed_at=?,batch_id='abandoned'",(self.now.timestamp()-mail.STALE_BATCH_SECONDS-1,))
            c.execute("UPDATE communication_attempts SET status='sending'");c.commit()
        with patch.object(mail,'_send_one') as send:
            self.assertEqual(reminders.run(core,self.now)['messages'],0);send.assert_not_called()
        self.assertTrue(all(h['status']=='uncertain' for h in reminders.overview(core,self.hr,self.now)['history']))


if __name__=='__main__':unittest.main()
