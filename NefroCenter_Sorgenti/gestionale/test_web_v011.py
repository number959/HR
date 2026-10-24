"""HTTP integration: routes, scoped access, freeze and automatic mail defaults."""
import base64
import unittest
import core, hr
import test_web as fixture


class WebV011Tests(unittest.TestCase):
    setUp=fixture.WebTests.setUp
    tearDown=fixture.WebTests.tearDown
    enroll=fixture.WebTests.enroll
    new_user=fixture.WebTests.new_user

    def test_integrated_defaults_and_new_assets(self):
        self.enroll()
        for path in ('/api/approvals?cid='+self.cid+'&month=2026-10',
                     '/api/staffing?cid='+self.cid+'&month=2026-10',
                     '/api/reminders','/api/departures','/api/payroll_specification?cid='+self.cid):
            self.assertIsInstance(self.client.ok(path),dict,path)
        policy=self.client.ok('/api/approvals?cid='+self.cid+'&month=2026-10')['policy']
        self.assertFalse(policy['enabled'])
        for asset in ('approvals','reminders','staffing','departures'):
            for ext in ('js','css'):
                self.assertTrue(self.client.ok('/assets/'+asset+'.'+ext))
        self.assertEqual(self.client.ok('/health')['version'],'0.11')

    def test_operator_private_routes_and_scope(self):
        self.enroll();code=self.new_user('operator');client=fixture.Client(self.web);self.enroll(client,'operator',code)
        other=core.mutate(self.admin,'center_create',dict(name='Sede remota',code='REM'))['cid']
        for path in ('/api/reminders','/api/departures','/api/hr_document_review?cid='+self.cid+'&id=missing','/api/payroll_specification?cid='+self.cid):
            self.assertEqual(client.call(path)[0],403,path)
        for module in ('approvals','staffing'):
            self.assertEqual(client.call('/api/'+module+'?cid='+other+'&month=2026-10')[0],403,module)
        for route in ('reminder_config_save','departure_case_save','equipment_save','staffing_requirements_save','approval_config_save'):
            self.assertEqual(client.call('/api/'+route,{'cid':self.cid})[0],403,route)
        aggregate=client.ok('/api/staffing?cid='+self.cid+'&month=2026-10')
        self.assertFalse(aggregate['permissions']['availability'])

    def test_admin_configuration_requires_recent_factor(self):
        self.enroll();self.clock+=601
        for action in ('approval_config_save','reminder_config_save'):
            self.assertEqual(self.client.call('/api/'+action,{'cid':self.cid})[0],428)

    def test_document_review_http_and_filter(self):
        self.enroll()
        pid=hr.save(core,self.admin,dict(cid=self.cid,revision=0,version=0,name='Persona prova',role='INF',active=True,stage='active',fields={},custom={}))['pid']
        doc=self.client.ok('/api/hr_document_add',dict(cid=self.cid,pid=pid,name='prova.pdf',content=base64.b64encode(b'%PDF-1.4\nTest\n%%EOF').decode()))['id']
        read=self.client.ok('/api/hr_document_review?cid='+self.cid+'&id='+doc)
        reviewed=self.client.ok('/api/hr_document_review',dict(cid=self.cid,id=doc,version=read['review']['version'],status='verified',note='Documento controllato'))
        self.assertEqual(reviewed['review']['status'],'verified')
        self.assertEqual(len(self.client.ok('/api/hr_documents?review=verified')['documents']),1)
        self.assertEqual(len(self.client.ok('/api/hr_documents?review=received')['documents']),0)
        self.assertEqual(self.client.call('/api/hr_document_review',dict(cid=self.cid,id=doc,version=read['review']['version'],status='needs_correction',note='Versione precedente'))[0],400)

    def test_workflow_freeze_through_http(self):
        self.enroll();month='2026-10'
        core.mutate(self.admin,'person',dict(cid=self.cid,month=month,revision=0,person=dict(name='Persona demo',role='INF',active=True)))
        snap=core.snapshot(self.admin,self.cid,month)
        core.mutate(self.admin,'entry',dict(cid=self.cid,month=month,revision=snap['center']['revision'],entry=dict(person_id=snap['people'][0]['id'],day=month+'-14',slot='m',code='m',layer='actual')))
        self.client.ok('/api/approval_config_save',dict(cid=self.cid,version=0,enabled=True,reason='Avvio controllo mensile'))
        state=self.client.ok('/api/approvals?cid='+self.cid+'&month='+month)
        result=self.client.ok('/api/approval_transition',dict(cid=self.cid,month=month,version=state['workflow']['version'],fingerprint=state['fingerprint'],action='submit',note='Invio per controllo'))
        self.assertEqual(result['workflow']['status'],'submitted')
        snapshot=self.client.ok('/api/state?cid='+self.cid+'&month='+month)
        self.assertTrue(snapshot['approval']['frozen'])
        for action in ('close','reopen','period_verify'):
            self.assertEqual(self.client.call('/api/'+action,dict(cid=self.cid,month=month,revision=snapshot['center']['revision'],verified=True,reason='Prova aggiramento'))[0],400)
        self.client.ok('/api/approval_transition',dict(cid=self.cid,month=month,version=result['workflow']['version'],fingerprint=result['fingerprint'],action='return',note='Completare registrazioni'))
        self.assertFalse(self.client.ok('/api/state?cid='+self.cid+'&month='+month)['approval']['frozen'])
