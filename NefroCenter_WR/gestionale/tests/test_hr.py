import unittest

from support import PortalCase

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


class HRCase(PortalCase):
    def setUp(self):
        super().setUp()
        self.cid = self.portal.center('Centro Dialisi Est', 'EST')
        self.manager = self.portal.user('responsabile', 'manager', [self.cid])
        self.operator = self.portal.user('compilatore', 'operator', [self.cid])
        self.hr = self.portal.user('hrcentrale', 'hr')

    def new_employee(self, client=None, **fields):
        body = {'name': 'Giulia Neri', 'role': 'INF', 'registration': 'H100', 'stage': 'incoming', 'version': 0,
                'fields': {'first_name': 'Giulia', 'last_name': 'Neri', 'start_date': '2026-11-02', **fields}}
        return (client or self.hr).post(f'/api/hr/{self.cid}', body)

    def upload(self, client, pid, data=PDF, name='contratto.pdf', ctype='application/pdf', **query):
        params = '&'.join([f'name={name}'] + [f'{k}={v}' for k, v in query.items()])
        return client.request('POST', f'/api/hr/{self.cid}/{pid}/documents?{params}', raw=data, content_type=ctype)


class Profiles(HRCase):
    def test_hr_creates_employee_with_onboarding_tasks(self):
        created = self.new_employee()
        self.assertEqual(created.status, 200, created.body)
        pid = created.data['person_id']
        detail = self.hr.ok('GET', f'/api/hr/{self.cid}/{pid}')
        self.assertEqual(detail['profile']['version'], 1)
        self.assertEqual(len(detail['tasks']), 14)
        identita = next(t for t in detail['tasks'] if t['id'] == 'identita')
        self.assertEqual(identita['due'], '2026-10-26', 'sette giorni prima dell’ingresso')
        # La persona compare anche nel registro presenze della struttura.
        people = self.manager.ok('GET', f'/api/centers/{self.cid}/people')['people']
        self.assertIn('Giulia Neri', [p['name'] for p in people])

    def test_field_validation(self):
        self.assertStatus(self.new_employee(iban='IT60X0542811101000000123457'), 400, 'IBAN')
        self.assertEqual(self.new_employee(iban='IT60 X054 2811 1010 0000 0123 456').status, 200)
        self.assertStatus(self.new_employee(tax_code='ABC'), 400, 'codice fiscale')
        self.assertStatus(self.new_employee(email='non-valida'), 400, 'email')
        self.assertStatus(self.new_employee(end_date='2026-01-01'), 400, 'precede')

    def test_operator_and_viewer_have_no_access(self):
        self.assertStatus(self.operator.get(f'/api/hr/{self.cid}'), 403)
        viewer = self.portal.user('direzione', 'viewer', [self.cid])
        self.assertStatus(viewer.get('/api/documents'), 403)

    def test_task_update_and_versioning(self):
        pid = self.new_employee().data['person_id']
        url = f'/api/hr/{self.cid}/{pid}/tasks/privacy'
        self.assertStatus(self.hr.put(url, {'status': 'na', 'version': 1}), 400, 'non è applicabile')
        done = self.hr.ok('PUT', url, {'status': 'done', 'version': 1})
        self.assertEqual(done['version'], 2)
        self.assertStatus(self.hr.put(url, {'status': 'todo', 'version': 1}), 409)
        detail = self.hr.ok('GET', f'/api/hr/{self.cid}/{pid}')
        task = next(t for t in detail['tasks'] if t['id'] == 'privacy')
        self.assertEqual((task['status'], task['done_by']), ('done', 'hrcentrale'))
        self.assertEqual(detail['progress']['done'], 1)
        self.assertEqual([h['version'] for h in detail['history']], [2, 1])

    def test_template_and_custom_fields(self):
        listing = self.manager.ok('GET', f'/api/hr/{self.cid}')
        template = listing['template']
        self.portal.step_up(self.manager)
        self.manager.ok('PUT', f'/api/hr/{self.cid}/template', {
            'version': template['version'], 'tasks': template['tasks'][:2],
            'fields': [{'id': 'taglia', 'label': 'Taglia divisa', 'type': 'text', 'required': True}]})
        pid = self.new_employee(self.manager).data['person_id']
        detail = self.manager.ok('GET', f'/api/hr/{self.cid}/{pid}')
        self.assertEqual(len(detail['tasks']), 2)
        self.assertEqual(detail['missing'], ['Taglia divisa'])

    def test_tax_code_unique_in_center(self):
        self.new_employee(tax_code='RSSMRA80A01H501U')
        other = {'name': 'Altro', 'role': 'INF', 'version': 0, 'fields': {'tax_code': 'RSSMRA80A01H501U'}}
        self.assertStatus(self.hr.post(f'/api/hr/{self.cid}', other), 400, 'Codice fiscale già presente')


class Documents(HRCase):
    def test_upload_view_and_central_review(self):
        pid = self.new_employee().data['person_id']
        uploaded = self.upload(self.manager, pid, category='Contratto', expiry='2030-01-01')
        self.assertEqual(uploaded.status, 200, uploaded.body)
        doc_id = uploaded.data['id']
        view = self.manager.get(f'/api/documents/{self.cid}/{doc_id}/content')
        self.assertEqual(view.status, 200)
        self.assertEqual(view.body, PDF)
        self.assertIn('sandbox', view.header('Content-Security-Policy'))
        self.assertTrue(view.header('Content-Disposition').startswith('inline'))
        review_url = f'/api/documents/{self.cid}/{doc_id}/review'
        self.assertStatus(self.manager.post(review_url, {'status': 'verified', 'version': 1}), 403)
        self.assertStatus(self.hr.post(review_url, {'status': 'needs_correction', 'version': 1, 'note': 'poco'}), 400)
        state = self.hr.ok('POST', review_url, {'status': 'needs_correction', 'version': 1, 'note': 'Manca la firma a pagina 2'})
        self.assertTrue(state['can_resubmit'])
        resubmitted = self.manager.ok('POST', review_url, {'status': 'received', 'version': 2, 'note': 'Caricata copia firmata'})
        self.assertEqual(resubmitted['review']['status'], 'received')
        verified = self.hr.ok('POST', review_url, {'status': 'verified', 'version': 3})
        self.assertEqual([h['status'] for h in verified['history']], ['verified', 'received', 'needs_correction', 'received'])
        archive = self.hr.ok('GET', '/api/documents?review=verified')
        self.assertEqual(archive['total'], 1)
        self.assertEqual(archive['documents'][0]['center'], 'Centro Dialisi Est')

    def test_upload_checks(self):
        pid = self.new_employee().data['person_id']
        self.assertStatus(self.upload(self.hr, pid, data=b'MZ' + b'\x00' * 10), 400, 'non corrisponde')
        self.assertStatus(self.upload(self.hr, pid, name='script.js'), 400, 'PDF, PNG o JPEG')
        self.assertStatus(self.upload(self.hr, pid, ctype='text/html'), 415)
        self.assertStatus(self.upload(self.hr, pid, data=b'%PDF-' + b'0' * (6 * 1024 * 1024)), 413)
        self.assertEqual(self.upload(self.hr, pid, data=PNG, name='badge.png', ctype='image/png').status, 200)
        self.assertStatus(self.upload(self.operator, pid), 403)

    def test_expired_document_cannot_be_verified(self):
        pid = self.new_employee().data['person_id']
        doc_id = self.upload(self.hr, pid, expiry='2020-01-01').data['id']
        response = self.hr.post(f'/api/documents/{self.cid}/{doc_id}/review', {'status': 'verified', 'version': 1})
        self.assertStatus(response, 400, 'scaduto')
        archive = self.hr.ok('GET', '/api/documents?expiry=expired')
        self.assertEqual(archive['total'], 1)
        self.assertTrue(archive['documents'][0]['late'])

    def test_delete_requires_reason_and_is_audited(self):
        pid = self.new_employee().data['person_id']
        doc_id = self.upload(self.hr, pid).data['id']
        self.assertStatus(self.hr.delete(f'/api/documents/{self.cid}/{doc_id}', {'reason': 'no'}), 400)
        self.hr.ok('DELETE', f'/api/documents/{self.cid}/{doc_id}', {'reason': 'Caricato per errore su altra persona'})
        self.assertStatus(self.hr.get(f'/api/documents/{self.cid}/{doc_id}/content'), 404)
        with self.portal.db.read() as con:
            actions = [r[0] for r in con.execute('SELECT action FROM audit WHERE entity_id=?', (doc_id,))]
        self.assertIn('Documento rimosso', actions)

    def test_document_needs_saved_profile(self):
        pid = self.manager.ok('POST', f'/api/centers/{self.cid}/people', {'name': 'Senza Fascicolo', 'role': 'OSS'})['id']
        self.assertStatus(self.upload(self.manager, pid), 400, 'Salvare il fascicolo')


if __name__ == '__main__':
    unittest.main()
