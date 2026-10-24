"""Meaningful email isolation and delivery state tests; no network is used."""
import copy
import json
import smtplib
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import Mock, patch

import communications as mail
import core
import hr
import structures
from rules import defaults


class CommunicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.old = core.DB
        core.DB = Path(self.temp.name) / 'test.sqlite3'; core.init_db()
        structures.init(core); mail.init(core)
        self.a, self.b = 'center-a', 'center-b'
        with core.connect() as c:
            for cid in (self.a, self.b):
                c.execute('INSERT INTO centers VALUES(?,?,?,?,?,?)', (cid, cid, cid, core.dump(defaults()), 1, 0))
                c.execute('INSERT INTO structure_profiles VALUES(?,?,?)', (cid, 1, core.dump({'hr_email': cid + '@example.com', 'email': cid + '@example.org'})))
            for role in ('admin', 'hr', 'manager', 'operator', 'viewer'):
                c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)', (role, role, role, role, core.dump([self.a]), 1, '{}'))
            c.commit()
            self.users = {r: core.public_user(c.execute('SELECT * FROM users WHERE id=?', (r,)).fetchone()) for r in ('admin', 'hr', 'manager', 'operator', 'viewer')}
        self.admin = self.users['admin']; self.hr = self.users['hr']
        self.person('p1', self.a, 'a@example.com')
        self.person('p2', self.b, 'b@example.com', role='MED')
        self.env = patch.dict('os.environ', {}, clear=True); self.env.start()
        self.addCleanup(self.env.stop)
        self.list = mail.save_list(core, self.hr, dict(version=0, name='Attivi', cids=[], roles=[], stages=['active'], email_field='company_email', exclude_emails=[], recipient_type='employees', structure_field='email'))
        self.template = mail.save_template(core, self.hr, dict(version=0, name='Prova', subject='Messaggio {{struttura}}', body='Gentile {{nome}}, contatta {{email_hr}}.'))

    def tearDown(self):
        core.DB = self.old; self.temp.cleanup()

    def person(self, pid, cid, email, **extra):
        with core.connect() as c:
            core.put(c, 'people', cid, dict(id=pid, name='Persona ' + pid, role=extra.get('role', 'INF'), registration=pid, active=True))
            data = dict(fields=dict(company_email=email, email=extra.get('personal', '')), tasks=[], custom={}, stage=extra.get('stage', 'active'))
            c.execute('INSERT INTO hr_profiles VALUES(?,?,?,?) ON CONFLICT(cid,pid) DO UPDATE SET data=excluded.data', (cid, pid, 1, core.dump(data)))
            c.commit()

    def request(self, **extra):
        return dict(template_id=self.template['id'], list_id=self.list['id'], **extra)

    def draft(self, **extra):
        body = self.request(**extra); view = mail.preview(core, self.hr, body)
        return mail.create_campaign(core, self.hr, {**body, 'fingerprint': view['fingerprint']})

    def config(self, **extra):
        config = {**mail.DEFAULT_SETTINGS, 'version': mail.overview(core, self.admin)['settings']['version'], 'enabled': True, 'host': 'smtp.example.com', 'from_email': 'hr@example.com'}
        config.update(extra)
        return mail.save_configuration(core, self.admin, config)

    def send(self, campaign, **extra):
        return mail.send_campaign(core, self.hr, dict(id=campaign['id'], confirm=True, confirmation_token=campaign['confirmation_token'], **extra))

    def test_defaults_allow_drafts_but_never_send(self):
        self.assertEqual(len(mail.overview(core, self.hr)['templates']), 6)
        draft = self.draft(); self.assertEqual(draft['counts']['pending'], 2)
        with patch.object(mail, '_send_one') as send, self.assertRaisesRegex(ValueError, 'disabilitato'):
            self.send(draft)
        send.assert_not_called()
        self.assertFalse(mail.overview(core, self.hr)['settings']['enabled'])

    def test_permissions_reloaded_for_every_operation_and_hr_config_redacted(self):
        self.config(username='login@example.com')
        self.assertEqual(set(mail.overview(core, self.hr)['settings']), {'enabled', 'configured', 'batch_size'})
        for role in ('manager', 'operator', 'viewer'):
            with self.assertRaises(PermissionError): mail.overview(core, self.users[role])
            with self.assertRaises(PermissionError): mail.preview(core, self.users[role], self.request())
        with self.assertRaises(PermissionError): mail.save_configuration(core, self.hr, {})
        with core.connect() as c:
            c.execute("UPDATE users SET role='viewer' WHERE id='hr'"); c.commit()
        with self.assertRaises(PermissionError): mail.preview(core, self.hr, self.request())
        with core.connect() as c:
            c.execute("UPDATE users SET active=0 WHERE id='hr'"); c.commit()
        with self.assertRaises(core.AuthenticationError): mail.overview(core, self.hr)

    def test_filters_are_scoped_to_centers_roles_stage_and_reject_unknown_center(self):
        row = mail.save_list(core, self.hr, {**self.list, 'cids': [self.b], 'roles': ['MED']})
        self.list = row
        p = mail.preview(core, self.hr, self.request())
        self.assertEqual([(r['cid'], r['pid']) for r in p['recipients']], [(self.b, 'p2')])
        with self.assertRaises(ValueError): mail.save_list(core, self.hr, {**row, 'cids': ['unknown']})
        with self.assertRaises(ValueError): mail.save_list(core, self.hr, {**row, 'recipient_type': 'structures'})

    def test_dedup_invalid_missing_and_exclusions_are_visible(self):
        self.person('duplicate', self.a, 'A@EXAMPLE.COM')
        self.person('bad', self.a, 'wrong\r\nBcc: victim@example.com')
        self.person('missing', self.a, '')
        self.list = mail.save_list(core, self.hr, {**self.list, 'exclude_emails': ['B@example.com']})
        p = mail.preview(core, self.hr, self.request())
        self.assertEqual(p['counts'], dict(selected=5, valid=1, missing=1, invalid=1, duplicates=1, excluded=1))
        self.assertTrue(p['can_create'])
        self.assertEqual({w['code'] for w in p['warnings']}, {'missing_email', 'invalid_email', 'duplicate_email'})

    def test_structure_audience_and_current_structure_variables(self):
        self.list = mail.save_list(core, self.hr, {**self.list, 'recipient_type': 'structures', 'structure_field': 'hr_email', 'stages': []})
        p = mail.preview(core, self.hr, self.request())
        self.assertEqual(len(p['recipients']), 2)
        self.assertTrue(all(not r['pid'] for r in p['recipients']))
        self.assertEqual({r['email'] for r in p['recipients']}, {'center-a@example.com', 'center-b@example.com'})

    def test_template_header_injection_unknown_missing_variables_block(self):
        for subject in ('Bad\r\nBcc: victim@example.com', 'Unknown {{password}}', 'Malformed {{nome'):
            with self.assertRaises(ValueError): mail.save_template(core, self.hr, {**self.template, 'subject': subject})
        p = mail.preview(core, self.hr, self.request(body='Gentile {{cognome}}'))
        self.assertFalse(p['can_create'])
        self.assertIn('missing_variable', {w['code'] for w in p['warnings']})
        with self.assertRaises(ValueError): mail.create_campaign(core, self.hr, {**self.request(body='Gentile {{cognome}}'), 'fingerprint': p['fingerprint']})
        with core.connect() as c:
            person = core.objects(c, 'people', self.a)[0]; person['name'] = 'Bad\nBcc: victim@example.com'; core.put(c, 'people', self.a, person); c.commit()
        self.assertFalse(mail.preview(core, self.hr, self.request(subject='Ciao {{nome}}'))['can_create'])

    def test_versions_and_changed_preview_reject_stale_writes(self):
        mail.save_template(core, self.hr, {**self.template, 'name': 'Nuovo'})
        with self.assertRaisesRegex(ValueError, 'versione'): mail.save_template(core, self.hr, self.template)
        p = mail.preview(core, self.hr, self.request())
        self.person('p1', self.a, 'changed@example.com')
        with self.assertRaisesRegex(ValueError, 'cambiati'): mail.create_campaign(core, self.hr, {**self.request(), 'fingerprint': p['fingerprint']})
        self.list = mail.save_list(core, self.hr, {**self.list, 'name': 'Lista cambiata'})
        with self.assertRaises(ValueError): mail.save_list(core, self.hr, {**self.list, 'version': self.list['version'] - 1})

    def test_campaign_is_immutable_snapshot_when_contacts_or_templates_change(self):
        draft = self.draft(subject='Oggetto scritto a mano', body='Buongiorno {{nome}}')
        self.person('p1', self.a, 'changed@example.com')
        mail.save_template(core, self.hr, {**self.template, 'subject': 'Nuova versione'})
        stored = mail.campaign(core, self.hr, draft['id'])
        self.assertEqual(stored['recipients'], draft['recipients'])
        self.assertEqual(stored['subject'], 'Oggetto scritto a mano')

    def test_configuration_tls_required_secret_only_env_and_header_injection(self):
        for change in ({'security': 'plain'}, {'from_email': 'hr@example.com\r\nBcc: victim@example.com'}, {'host': 'https://smtp.example.com'}, {'password': 'secret'}, {'batch_size': 21}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.config(**change)
        cfg = self.config(username='user'); self.assertFalse(cfg['configured'])
        with patch.dict('os.environ', {mail.PASSWORD_ENV: 'top-secret'}):
            self.assertTrue(mail.overview(core, self.admin)['settings']['configured'])
            with core.connect() as c:
                stored = str([tuple(r) for r in c.execute('SELECT * FROM communication_settings')]) + str([tuple(r) for r in c.execute('SELECT * FROM audit')])
            self.assertNotIn('top-secret', stored)
            self.assertNotIn('top-secret', core.dump(mail.overview(core, self.admin)))

    def test_confirmation_token_batch_limit_and_serial_replay(self):
        self.config(batch_size=1); draft = self.draft()
        self.assertEqual(draft['send_plan']['count'], 1)
        with patch.object(mail, '_send_one', return_value=('accepted', '')) as send:
            with self.assertRaises(ValueError): mail.send_campaign(core, self.hr, dict(id=draft['id'], confirm=False))
            sent = self.send(draft)
            self.assertEqual((sent['counts']['accepted'], sent['counts']['pending']), (1, 1))
            with self.assertRaisesRegex(ValueError, 'cambiati'): self.send(draft)
            self.assertEqual(send.call_count, 1)
            done = self.send(sent)
            self.assertEqual(done['counts']['accepted'], 2)
            with self.assertRaises(ValueError): self.send(done)

    def test_concurrent_same_campaign_cannot_duplicate_or_send_unconfirmed_next_batch(self):
        self.config(batch_size=1); draft = self.draft(); entered = threading.Event(); release = threading.Event()
        def fake(*args):
            entered.set(); release.wait(5); return 'accepted', ''
        with patch.object(mail, '_send_one', side_effect=fake) as send, ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.send, draft); self.assertTrue(entered.wait(3))
            with self.assertRaises(ValueError): self.send(draft)
            release.set(); result = future.result(5)
        self.assertEqual(send.call_count, 1); self.assertEqual(result['counts']['pending'], 1)

    def test_failed_can_retry_explicitly_uncertain_and_accepted_never_retry(self):
        self.config(); draft = self.draft()
        with patch.object(mail, '_send_one', side_effect=[('failed', 'Rifiutato'), ('uncertain', 'Esito incerto')]):
            result = self.send(draft)
        with patch.object(mail, '_send_one', return_value=('accepted', '')) as send:
            with self.assertRaises(ValueError): self.send(result)
            retried = self.send(result, retry_failed=True)
            self.assertEqual(send.call_count, 1)
            self.assertEqual((retried['counts']['accepted'], retried['counts']['uncertain']), (1, 1))
            with self.assertRaises(ValueError): self.send(retried, retry_failed=True)
        self.assertEqual([len(r['attempts']) for r in retried['recipients']], [2, 1])

    def test_rate_budget_counts_claimed_failed_attempts_and_configuration_changes_invalidate_token(self):
        self.config(max_per_hour=1); draft = self.draft()
        with patch.object(mail, '_send_one', return_value=('failed', 'Rifiutato')):
            sent = self.send(draft)
            self.assertEqual(sent['counts']['failed'], 1)
            with self.assertRaisesRegex(ValueError, 'Limite'): self.send(sent)
        self.config(max_per_hour=10)
        with self.assertRaisesRegex(ValueError, 'cambiati'): self.send(sent)

    def test_smtp_individual_to_tls_crlf_and_accepted_is_not_delivery_confirmation(self):
        cfg = {**mail.DEFAULT_SETTINGS, 'host': 'smtp.example.com', 'from_email': 'hr@example.com', 'username': 'smtp-user', 'reply_to': 'reply@example.com'}
        recipient = self.draft()['recipients'][0]; smtp = Mock(); smtp.mail.return_value = (250, b'ok'); smtp.rcpt.return_value = (250, b'ok'); smtp.data.return_value = (250, b'accepted')
        with patch.dict('os.environ', {mail.PASSWORD_ENV: 'secret-value'}), patch.object(mail.smtplib, 'SMTP_SSL', return_value=smtp) as factory:
            status, error = mail._send_one(cfg, recipient, '<unit@example.com>')
        self.assertEqual((status, error), ('accepted', '')); smtp.login.assert_called_once_with('smtp-user', 'secret-value')
        context = factory.call_args.kwargs['context']; self.assertTrue(context.check_hostname)
        raw = smtp.data.call_args.args[0]; self.assertNotIn(b'\n', raw.replace(b'\r\n', b''))
        parsed = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertEqual(parsed['To'], recipient['email']); self.assertIsNone(parsed['Cc']); self.assertIsNone(parsed['Bcc'])
        self.assertEqual(parsed['Message-ID'], '<unit@example.com>')
        smtp.rcpt.assert_called_once_with(recipient['email'])
        with patch.object(mail.smtplib, 'SMTP', return_value=smtp):
            mail._send_one({**cfg, 'security': 'starttls'}, recipient, '<unit2@example.com>')
        smtp.starttls.assert_called_once()

    def test_smtp_failure_before_data_is_retryable_but_disconnect_after_data_is_uncertain(self):
        cfg = {**mail.DEFAULT_SETTINGS, 'host': 'smtp.example.com', 'from_email': 'hr@example.com'}
        recipient = self.draft()['recipients'][0]
        with patch.object(mail.smtplib, 'SMTP_SSL', side_effect=OSError('secret-password@example.com')):
            status, error = mail._send_one(cfg, recipient, '<a@example.com>')
        self.assertEqual(status, 'failed'); self.assertNotIn('secret-password', error)
        smtp = Mock(); smtp.mail.return_value = (250, b'ok'); smtp.rcpt.return_value = (250, b'ok'); smtp.data.side_effect = smtplib.SMTPServerDisconnected('password SECRET')
        with patch.object(mail.smtplib, 'SMTP_SSL', return_value=smtp): status, error = mail._send_one(cfg, recipient, '<b@example.com>')
        self.assertEqual(status, 'uncertain'); self.assertNotIn('SECRET', error)
        smtp.data.side_effect = smtplib.SMTPDataError(554, b'SECRET')
        with patch.object(mail.smtplib, 'SMTP_SSL', return_value=smtp): self.assertEqual(mail._send_one(cfg, recipient, '<c@example.com>')[0], 'failed')

    def test_crash_claim_is_durable_and_never_retried(self):
        self.config(batch_size=1); draft = self.draft()
        with patch.object(mail, '_send_one', side_effect=RuntimeError('crash')), self.assertRaises(RuntimeError): self.send(draft)
        stuck = mail.campaign(core, self.hr, draft['id']); self.assertEqual(stuck['counts']['sending'], 1)
        self.assertFalse(stuck['can_reconcile'])
        with self.assertRaises(ValueError):mail.reconcile_campaign(core,self.hr,{'id':draft['id']})
        with core.connect() as c:
            c.execute('UPDATE communication_recipients SET claimed_at=? WHERE status=\'sending\'', (time.time() - mail.STALE_BATCH_SECONDS - 1,)); c.commit()
        with patch.object(mail, '_send_one', return_value=('accepted', '')) as send:
            self.assertTrue(mail.campaign(core,self.hr,draft['id'])['can_reconcile'])
            stuck=mail.reconcile_campaign(core,self.hr,{'id':draft['id']})
            send.assert_not_called()
            resumed = self.send(stuck)
        self.assertEqual(send.call_count, 1)
        self.assertEqual((resumed['counts']['uncertain'], resumed['counts']['accepted']), (1, 1))
        self.assertEqual([len(r['attempts']) for r in resumed['recipients']], [1, 1])


if __name__ == '__main__':
    unittest.main()
