import unittest
from datetime import datetime

from support import PortalCase
from wr import reminders
from wr.util import ZONE


class FakeTransport:
    """Sostituisce il server di posta: nessuna connessione di rete."""

    def __init__(self, outcome=('accepted', '')):
        self.sent = []
        self.outcome = outcome

    def __call__(self, cfg, recipient, message_id):
        self.sent.append((recipient['email'], recipient['subject']))
        return self.outcome


class MailCase(PortalCase):
    def setUp(self):
        super().setUp()
        self.cid = self.portal.center('Centro Dialisi Est', 'EST')
        self.hr = self.portal.user('hrcentrale', 'hr')
        self.transport = FakeTransport()
        self.portal.app.services['mail_transport'] = self.transport
        for name, email in (('Giulia Neri', 'giulia.neri@example.org'), ('Paolo Blu', ''), ('Zeno Doppio', 'GIULIA.NERI@example.org')):
            self.hr.ok('POST', f'/api/hr/{self.cid}', {'name': name, 'role': 'INF', 'version': 0, 'stage': 'active',
                                                      'fields': {'company_email': email, 'first_name': name.split()[0]}})

    def make_list(self):
        return self.hr.ok('POST', '/api/mail/lists', {'name': 'Infermieri', 'cids': [self.cid], 'roles': ['INF'],
                                                      'version': 0})['id']

    def configure_smtp(self, enabled=True):
        current = self.admin.ok('GET', '/api/mail')['settings']
        self.portal.step_up(self.admin)
        return self.admin.put('/api/mail/settings', {
            'enabled': enabled, 'host': 'posta.esempio.invalid', 'port': 465, 'security': 'ssl', 'username': '',
            'from_email': 'hr@esempio.invalid', 'from_name': 'Ufficio HR', 'reply_to': '', 'batch_size': 20,
            'max_per_hour': 100, 'version': current['version']})


class Campaigns(MailCase):
    def test_seed_templates_and_preview(self):
        overview = self.hr.ok('GET', '/api/mail')
        self.assertEqual(len(overview['templates']), 5)
        self.assertFalse(overview['settings']['enabled'])
        preview = self.hr.ok('POST', '/api/mail/preview', {'template_id': 'seed-benvenuto', 'list_id': self.make_list()})
        self.assertEqual(preview['counts']['valid'], 1)
        self.assertEqual(preview['counts']['missing'], 1)
        self.assertEqual(preview['counts']['duplicates'], 1)
        self.assertIn('Giulia Neri', preview['recipients'][0]['body'])

    def test_unknown_variable_rejected(self):
        response = self.hr.post('/api/mail/templates', {'name': 'Prova', 'subject': 'Ciao {{nome}}', 'body': 'Testo {{iban}}',
                                                        'version': 0})
        self.assertStatus(response, 400, 'Variabile')

    def test_draft_then_send_only_when_enabled_and_confirmed(self):
        list_id = self.make_list()
        preview = self.hr.ok('POST', '/api/mail/preview', {'template_id': 'seed-benvenuto', 'list_id': list_id})
        draft = self.hr.ok('POST', '/api/mail/campaigns', {'template_id': 'seed-benvenuto', 'list_id': list_id,
                                                           'fingerprint': preview['fingerprint']})
        self.assertEqual(draft['status'], 'draft')
        self.assertFalse(draft['can_send'], 'posta non configurata: solo bozza')
        self.portal.step_up(self.hr)
        refused = self.hr.post(f'/api/mail/campaigns/{draft["id"]}/send', {'confirm': True, 'confirmation_token': draft['confirmation_token']})
        self.assertStatus(refused, 400, 'disattivato')
        self.assertEqual(self.transport.sent, [])
        self.assertStatus(self.hr.put('/api/mail/settings', {}), 403)
        self.assertEqual(self.configure_smtp().status, 200)
        draft = self.hr.ok('GET', f'/api/mail/campaigns/{draft["id"]}')
        self.assertTrue(draft['can_send'])
        self.portal.step_up(self.hr)
        unconfirmed = self.hr.post(f'/api/mail/campaigns/{draft["id"]}/send', {'confirm': False, 'confirmation_token': draft['confirmation_token']})
        self.assertStatus(unconfirmed, 400)
        sent = self.hr.ok('POST', f'/api/mail/campaigns/{draft["id"]}/send', {'confirm': True,
                                                                               'confirmation_token': draft['confirmation_token']})
        self.assertEqual(sent['status'], 'accepted')
        self.assertEqual(self.transport.sent, [('giulia.neri@example.org', 'Benvenuto in Centro Dialisi Est')])

    def test_stale_fingerprint(self):
        list_id = self.make_list()
        preview = self.hr.ok('POST', '/api/mail/preview', {'template_id': 'seed-benvenuto', 'list_id': list_id})
        self.hr.ok('POST', f'/api/hr/{self.cid}', {'name': 'Nuova Persona', 'role': 'INF', 'version': 0, 'stage': 'active',
                                                  'fields': {'company_email': 'nuova@example.org'}})
        response = self.hr.post('/api/mail/campaigns', {'template_id': 'seed-benvenuto', 'list_id': list_id,
                                                        'fingerprint': preview['fingerprint']})
        self.assertStatus(response, 409)

    def test_manager_has_no_access(self):
        manager = self.portal.user('responsabile', 'manager', [self.cid])
        self.assertStatus(manager.get('/api/mail'), 403)


class Reminders(MailCase):
    def setUp(self):
        super().setUp()
        structure = self.hr.ok('GET', f'/api/structures/{self.cid}')['structure']
        fields = dict(structure['fields'], hr_email='hr.est@esempio.invalid')
        self.hr.ok('PUT', f'/api/structures/{self.cid}', {'fields': fields, 'version': structure['version']})
        pid = self.hr.ok('GET', f'/api/hr/{self.cid}')['employees'][0]['id']
        detail = self.hr.ok('GET', f'/api/hr/{self.cid}/{pid}')
        fields = dict(detail['profile']['fields'], end_date='2026-11-01')
        self.hr.ok('PUT', f'/api/hr/{self.cid}/{pid}', {'name': detail['person']['name'], 'role': 'INF', 'stage': 'active',
                                                       'fields': fields, 'version': detail['profile']['version']})

    def test_disabled_by_default_and_never_sends(self):
        overview = self.hr.ok('GET', '/api/reminders')
        self.assertFalse(overview['config']['enabled'])
        now = datetime(2026, 10, 25, 9, 0, tzinfo=ZONE)
        self.assertEqual(reminders.run(self.portal.db, now, self.transport)['state'], 'disabled')
        self.assertEqual(self.transport.sent, [])

    def test_enable_requires_preview_confirmation_and_smtp(self):
        form = dict(reminders.DEFAULTS, enabled=True)
        preview = self.hr.ok('POST', '/api/reminders/preview', form)
        self.assertTrue(preview['can_enable'])
        self.assertGreaterEqual(preview['pending_events'], 1)
        body = dict(form, version=0, fingerprint='0' * 64, confirmed=True)
        self.portal.step_up(self.admin)
        self.assertStatus(self.admin.put('/api/reminders', body), 400, 'anteprima')
        body['fingerprint'] = preview['fingerprint']
        self.assertStatus(self.admin.put('/api/reminders', body), 400, 'server di posta')
        self.configure_smtp()
        body['fingerprint'] = self.admin.ok('POST', '/api/reminders/preview', form)['fingerprint']
        self.portal.step_up(self.admin)
        self.assertEqual(self.admin.put('/api/reminders', body).status, 200)
        now = datetime(2026, 10, 25, 9, 0, tzinfo=ZONE)
        result = reminders.run(self.portal.db, now, self.transport)
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(len(self.transport.sent), 1)
        self.assertNotIn('Giulia', self.transport.sent[0][1])
        again = reminders.run(self.portal.db, now, self.transport)
        self.assertEqual(again['state'], 'no_work', 'nessun promemoria ripetuto')
        self.assertEqual(len(self.transport.sent), 1)


if __name__ == '__main__':
    unittest.main()
