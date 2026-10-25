import io
import unittest

import xlsxwriter

from support import PortalCase


def sodav_workbook(empty=False):
    """Cartella di lavoro sintetica con la stessa struttura del modello Sodav (dati fittizi)."""
    stream = io.BytesIO()
    wb = xlsxwriter.Workbook(stream, {'in_memory': True})
    ws = wb.add_worksheet('Da Compilare')
    ref = wb.add_worksheet('Foglio1')
    yellow = wb.add_format({'bg_color': '#FFFF00', 'pattern': 1})
    red = wb.add_format({'font_color': '#FF0000'})
    ref.write('I2', 'esterno', yellow)
    ref.write('M2', 'festivo', red)
    ws.write('C6', 'Centro Importato Prova')
    ws.write_number('O6', 46054)  # 1 febbraio 2026 (seriale Excel)
    ws.write_number('X3', 26)
    for i, (role, name) in enumerate((('INF', 'Rosa Gialli'), ('MED', 'Dario Verdi'))):
        r = 10 + i * 3
        ws.write(f'A{r}', role)
        ws.write(f'B{r}', name)
        ws.write(f'B{r + 1}', 'Tempo pieno')
        for j, slot in enumerate('mps'):
            ws.write(f'C{r + j}', slot)
        if not empty:
            ws.write(f'D{r}', 'm')
            ws.write(f'E{r}', 'm', yellow)
            ws.write(f'F{r + 1}', 'p', red)
            ws.write(f'G{r}', 'FE')
        end = r + 2
        ws.write_formula(f'AT{r}', f'93-COUNTBLANK(D{r}:AH{end})')
        ws.write_formula(f'AV{end}', f'IF(AT{r}<=0,"",AT{r}-X3)')
        ws.write_formula(f'AW{end}', f'IF(AV{end}="","",AV{end}-AY{end})')
        ws.write_formula(f'AX{end}', f'IF(AW{end}="","",AW{end}*50)')
        ws.write_formula(f'AZ{end}', f'IF(AY{end}="","",AY{end}*70)')
        ws.write_formula(f'BA{end}', f'IF(AX{end}="","",AX{end}+AZ{end}-100)')
    wb.close()
    return stream.getvalue()


class ExcelImport(PortalCase):
    def upload(self, data):
        self.portal.step_up(self.admin)
        return self.admin.request('POST', '/api/import/preview', raw=data, content_type='application/octet-stream')

    def test_preview_then_confirm_once(self):
        preview = self.upload(sodav_workbook())
        self.assertEqual(preview.status, 200, preview.body)
        data = preview.data
        self.assertEqual((data['center'], data['month'], data['people'], data['entries'], data['external']),
                         ('Centro Importato Prova', '2026-02', 2, 8, 2))
        self.assertEqual(data['proposals'], 2)
        self.assertTrue(any('X3 contiene 26' in w for w in data['warnings']))
        self.portal.step_up(self.admin)
        done = self.admin.ok('POST', '/api/import/confirm', {'key': data['key']})
        snap = self.admin.ok('GET', f'/api/attendance/{done["center_id"]}/2026-02')
        self.assertEqual(len(snap['entries']), 8)
        self.assertTrue(any('importate da verificare' in a['text'] for a in snap['alerts']))
        holiday = [e for e in snap['entries'] if e['holiday']]
        self.assertEqual(len(holiday), 2)
        agreements = self.admin.ok('GET', f'/api/agreements/{done["center_id"]}/2026-02')
        self.assertTrue(all(r['saved'] and not r['agreement']['confirmed'] for r in agreements['rows']))
        again = self.upload(sodav_workbook())
        self.portal.step_up(self.admin)
        repeat = self.admin.ok('POST', '/api/import/confirm', {'key': again.data['key']})
        self.assertTrue(repeat['already_imported'])

    def test_close_blocked_until_external_site_is_specified(self):
        data = self.upload(sodav_workbook()).data
        self.portal.step_up(self.admin)
        cid = self.admin.ok('POST', '/api/import/confirm', {'key': data['key']})['center_id']
        state = self.admin.ok('GET', f'/api/attendance/{cid}/2026-02')['state']
        state = self.admin.ok('POST', f'/api/attendance/{cid}/2026-02/verify', {'verified': True, 'version': state['version']})['state']
        response = self.admin.post(f'/api/attendance/{cid}/2026-02/close', {'version': state['version']})
        self.assertStatus(response, 400, 'importate da verificare')

    def test_rejects_other_files(self):
        self.assertStatus(self.upload(b'non un excel'), 400, 'cartella di lavoro')
        hr = self.portal.user('hrcentrale', 'hr')
        self.portal.step_up(hr)
        self.assertStatus(hr.request('POST', '/api/import/preview', raw=b'x', content_type='application/octet-stream'), 403)


if __name__ == '__main__':
    unittest.main()
