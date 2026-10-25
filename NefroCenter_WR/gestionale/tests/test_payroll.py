import copy
import unittest

from test_attendance import MONTH, AttendanceCase


class Payroll(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.hr = self.portal.user('hrcentrale', 'hr')
        self.url = f'/api/payroll/{self.cid}'

    def confirm_template(self, change=None):
        current = self.hr.ok('GET', self.url)
        cfg = copy.deepcopy(current['config'])
        cfg.update(status='confirmed', confirmation_note='Verificato con il consulente il 20/10/2026')
        cfg['causes'] = {c['id']: 'P' + c['id'] for c in current['causes']}
        if change:
            change(cfg)
        self.portal.step_up(self.hr)
        return self.hr.put(self.url, {'config': cfg, 'version': current['version']})

    def preview(self):
        return self.hr.ok('GET', f'{self.url}/preview?from={MONTH}&to={MONTH}')

    def test_draft_template_blocks_download(self):
        self.entry(self.manager)
        data = self.preview()
        self.assertFalse(data['can_download'])
        self.assertIn('unconfirmed_template', [i['code'] for i in data['issues']])

    def test_confirmed_template_and_export(self):
        self.entry(self.manager)
        self.assertEqual(self.confirm_template().status, 200)
        data = self.preview()
        self.assertTrue(data['can_download'], data['issues'])
        self.assertEqual(data['summary']['rows'], 1)
        self.portal.step_up(self.hr)
        csv_file = self.hr.get(f'{self.url}/export?from={MONTH}&to={MONTH}&format=csv&fingerprint={data["fingerprint"]}')
        self.assertEqual(csv_file.status, 200, csv_file.body)
        text = csv_file.body.decode('utf-8-sig')
        self.assertIn('M001', text)
        self.assertIn('Pm', text)
        xlsx = self.hr.get(f'{self.url}/export?from={MONTH}&to={MONTH}&format=xlsx&fingerprint={data["fingerprint"]}')
        self.assertTrue(xlsx.body.startswith(b'PK'))
        self.entry(self.manager, day='2026-10-06')
        stale = self.hr.get(f'{self.url}/export?from={MONTH}&to={MONTH}&format=csv&fingerprint={data["fingerprint"]}')
        self.assertStatus(stale, 409)

    def test_missing_registration_and_unmapped_cause_block(self):
        nobody = self.person('Senza Matricola', 'OSS')
        self.entry(self.manager, person=nobody)
        self.confirm_template(lambda cfg: cfg['causes'].update(m=''))
        codes = [i['code'] for i in self.preview()['issues']]
        self.assertIn('missing_registration', codes)
        self.assertIn('unmapped_cause', codes)

    def test_consultant_spec_preview_reads_only_headers(self):
        ok = self.hr.ok('POST', f'{self.url}/spec-preview', {'kind': 'csv_header', 'text': 'Matricola paghe;Data;Causale paghe;Ore'})
        self.assertFalse(ok['stored'])
        self.assertEqual(ok['unmapped'], 1)
        rows = self.hr.post(f'{self.url}/spec-preview', {'kind': 'csv_header', 'text': 'A;B;C\n1;2;3'})
        self.assertStatus(rows, 400, 'solo la riga delle intestazioni')
        formula = self.hr.post(f'{self.url}/spec-preview', {'kind': 'csv_header', 'text': '=A1;B;C'})
        self.assertStatus(formula, 400, 'formule')

    def test_unknown_provider_cannot_be_confirmed(self):
        def consultant(cfg):
            cfg['connector'].update(mode='consultant', provider='da definire', format_name='Tracciato', format_version='1',
                                    specification_reference='Email del consulente')
        response = self.confirm_template(consultant)
        self.assertStatus(response, 400)

    def test_operator_has_no_access(self):
        self.assertStatus(self.operator.get(self.url), 403)


if __name__ == '__main__':
    unittest.main()
