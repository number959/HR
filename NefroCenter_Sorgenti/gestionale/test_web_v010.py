"""HTTP boundary checks for structure contacts and outbound communications."""
import unittest
import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch
import core
import hr
import test_web as fixture


class WebV010Tests(unittest.TestCase):
    setUp = fixture.WebTests.setUp
    tearDown = fixture.WebTests.tearDown
    enroll = fixture.WebTests.enroll
    new_user = fixture.WebTests.new_user

    def test_structures_in_employee_profile_and_manager_center_scope(self):
        self.enroll()
        fields = {'legal_name': 'Società demo', 'hr_email': 'hr@example.invalid'}
        result = self.client.ok('/api/structure_save', dict(cid=self.cid, version=0, fields=fields))
        self.assertEqual(result['structure']['version'], 1)
        pid = hr.save(core, self.admin, dict(cid=self.cid, revision=0, version=0,
            name='Persona demo', role='INF', active=True, stage='active', fields={}, custom={}))['pid']
        profile = self.client.ok('/api/hr?cid='+self.cid+'&pid='+pid)
        self.assertEqual(profile['structure']['fields']['hr_email'], fields['hr_email'])
        other = core.mutate(self.admin, 'center_create', dict(name='Sede esterna', code='EXT'))['cid']
        activation = self.new_user('manager')
        manager = fixture.Client(self.web); self.enroll(manager, 'manager', activation)
        self.assertEqual(len(manager.ok('/api/structures')['structures']), 1)
        self.assertEqual(manager.call('/api/structures?cid='+other)[0], 403)
        self.assertEqual(manager.call('/api/structure_save', dict(cid=other, version=0, fields=fields))[0], 403)
        self.assertEqual(manager.call('/api/communications')[0], 403)

    def test_email_configuration_and_send_require_recent_second_factor(self):
        self.enroll()
        overview = self.client.ok('/api/communications')
        self.assertFalse(overview['settings']['enabled'])
        self.assertGreaterEqual(len(overview['templates']), 5)
        self.clock += 601
        for action in ('communication_send', 'communication_config_save'):
            self.assertEqual(self.client.call('/api/'+action, {})[0], 428)

    def test_operator_denied_and_hr_cannot_configure_mail_server(self):
        self.enroll()
        activation = self.new_user('operator')
        operator = fixture.Client(self.web); self.enroll(operator, 'operator', activation)
        for path in ('/api/structures', '/api/communications', '/api/communication_campaign?id=unknown'):
            self.assertEqual(operator.call(path)[0], 403)
        for action in ('structure_save', 'communication_template_save', 'communication_list_save',
                       'communication_preview', 'communication_campaign_create', 'communication_send'):
            body = {'cid':self.cid} if action == 'structure_save' else {}
            self.assertEqual(operator.call('/api/'+action, body)[0], 403)
        activation = self.client.ok('/api/user_save', {'user':{'username':'hrcentral','name':'HR centrale',
            'role':'hr','centers':[],'active':True,'password':fixture.PASSWORD}})['activation_code']
        central = fixture.Client(self.web); self.enroll(central, 'hrcentral', activation)
        data = central.ok('/api/communications')
        self.assertFalse(data['settings']['enabled'])
        self.assertNotIn('username', data['settings'])
        self.assertNotIn('host', data['settings'])
        self.assertEqual(central.call('/api/communication_config_save', {})[0], 403)
        self.assertEqual(central.call('/api/communication_send', {'id':'unknown','confirm':True})[0], 400)

    def test_new_assets_served_with_existing_allowlist(self):
        for name in ('structures.js','structures.css','communications.js','communications.css'):
            self.assertEqual(self.client.call('/assets/'+name)[0], 200)
        self.assertNotEqual(self.client.call('/assets/communications.py')[0], 200)

    def test_after_restore_disables_mail_and_suspends_old_pending_messages(self):
        import manage
        import communications
        self.enroll()
        hr.save(core, self.admin, dict(cid=self.cid, revision=0, version=0,
            name='Destinatario demo', role='INF', active=True, stage='active',
            fields={'company_email':'persona@example.invalid'}, custom={}))
        mailing_list=self.client.ok('/api/communication_list_save', dict(version=0,name='Lista demo',
            cids=[self.cid],roles=[],stages=[],email_field='company_email',recipient_type='employees',
            structure_field='email',exclude_emails=[]))
        request=dict(template_id='seed-benvenuto',list_id=mailing_list['id'])
        preview=self.client.ok('/api/communication_preview',request)
        draft=self.client.ok('/api/communication_campaign_create',{**request,'fingerprint':preview['fingerprint']})
        with core.connect() as c:
            settings={**communications.DEFAULT_SETTINGS,'enabled':True,'host':'smtp.example.invalid','from_email':'hr@example.invalid'}
            c.execute('INSERT INTO communication_settings VALUES(1,1,?)',(core.dump(settings),));c.commit()
        args=['manage.py','after-restore','--data-dir',str(core.DB.parent),'--key-file',str(self.key)]
        with patch('sys.argv',args),patch('builtins.input',return_value='CONFERMO'),redirect_stdout(io.StringIO()):
            manage.main()
        with core.connect() as c:
            settings=json.loads(c.execute('SELECT data FROM communication_settings').fetchone()[0])
            self.assertFalse(settings['enabled'])
            self.assertEqual(c.execute('SELECT status FROM communication_recipients WHERE campaign_id=?',(draft['id'],)).fetchone()[0],'uncertain')


if __name__ == '__main__':
    unittest.main()
