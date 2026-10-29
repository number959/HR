import io
import unittest

from support import PortalCase  # aggiunge anche le librerie incluse (vendor) al percorso

import xlsxwriter  # noqa: E402


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


def real_like_workbook(center='Centro Agosto Prova', month_serial=46235, extra_person=None, note='', patients_days=5):
    """Cartella di lavoro sintetica con le particolarità del modello reale (dati fittizi).

    Codici minuscoli, una cella con un numero, una formula nella griglia, codice di un'altra fascia, persona ripetuta
    con due ruoli (una volta con codici diversi nello stesso giorno), sezioni dipendenti/collaboratori, riga «Totali»,
    formule con i festivi CCNL, festività di un altro anno sotto l'etichetta «Festività», pazienti per fascia (con
    contumacia e tabella ripetuta), pazienti di riferimento e foglio «Collaboratori» con importi e IBAN fittizi.
    """
    stream = io.BytesIO()
    wb = xlsxwriter.Workbook(stream, {'in_memory': True})
    ws = wb.add_worksheet('Da Compilare')
    ref = wb.add_worksheet('Foglio1')
    yellow = wb.add_format({'bg_color': '#FFFF00', 'pattern': 1})
    red = wb.add_format({'font_color': '#FF0000'})
    ref.write('I2', 'esterno', yellow)
    ref.write('M2', 'festivo', red)
    ws.write('A6', 'CENTRO:'); ws.write('C6', center); ws.write('J6', 'MESE:'); ws.write_number('O6', month_serial)
    ws.write('X2', 'Giorni Lavorativi'); ws.write_formula('X3', 'NETWORKDAYS.INTL(O6,O6+30,11,B181:B195)', None, 26)
    ws.write('AD3', 'Posti Letto'); ws.write_number('AD4', 10); ws.write('AG3', 'Contumaciale'); ws.write_number('AG4', 1)
    ws.write('AJ3', 'Infermieri'); ws.write_number('AJ4', 5); ws.write('AM3', 'Medici'); ws.write_number('AM4', 20)
    if note:
        ws.write('AV2', note)

    def person(r, role, name, contract, cells=(), economic=None, agreement_note=''):
        ws.write(f'A{r}', role); ws.write(f'B{r}', name); ws.write(f'B{r + 1}', contract)
        for j, slot in enumerate('mps'):
            ws.write(f'C{r + j}', slot)
        for addr, value, fmt in cells:
            if isinstance(value, (int, float)):
                ws.write_number(addr, value, fmt)
            else:
                ws.write(addr, value, fmt)
        if agreement_note:
            ws.write(f'AU{r}', agreement_note)
        end = r + 2
        ws.write_formula(f'AT{r}', f'93-COUNTBLANK(D{r}:AH{end})-AN{r}')
        if economic:
            ws.write_formula(f'AV{end}', f'AT{r}' if economic == 'all' else f'IF(AT{r}<=0,"",AT{r}-$X$3)')
            ws.write_formula(f'AW{end}', f'IF(AV{end}="","",AV{end}-AY{end})')
            ws.write_formula(f'AX{end}', f'IF(AW{end}="","",AW{end}*50)')
            ws.write_formula(f'AZ{end}', f'IF(AY{end}="","",AY{end}*70)')
            tail = {'all': '', 'surplus': '-100', 'ccnl': '-100-70*BB' + str(end)}[economic]
            ws.write_formula(f'BA{end}', f'IF(AX{end}="","",AX{end}+AZ{end}{tail})')

    ws.write('A9', 'Personale Dipendente')
    person(10, 'INF', 'Rosa Gialli', 'T.I.-FULL TIME', [('D10', 'fe', None), ('E10', 'm', yellow), ('F10', 'm', None),
           ('L10', 'm', red), ('J11', 1, None), ('H12', 'p', None)], 'ccnl', '1000 Incentivo')
    ws.write_formula('K11', '1+1', None, 2)  # formula dentro la griglia delle presenze
    ws.write('BB10', 'x')  # un festivo già riconosciuto dal CCNL
    person(13, 'INF', 'Dario Verdi', 'T.D.- FULL TIME', [('F13', 'm', None), ('G13', 'm', None), ('H13', 'M', None)], 'ccnl')
    ws.write('A16', 'Totali turni Infermieri')
    person(17, 'AMM', 'Pia Monti', 'T.I.-FULL TIME', [('F17', 'm', None)])
    ws.write('A20', 'Infermeri a prestazione/Volontari/Dipendenti altri centri')
    person(21, 'INF', 'Nora Fiume', 'FATTURA', [('F21', 'm', None), ('G21', 'm', None), ('F22', 'p', None), ('G23', 's', None),
           ('H23', 's', None)], 'all')
    person(24, 'AUT', 'Ugo Prati', 'ASS. ROSSI')
    ws.write('A27', 'Medici Dipendenti')
    person(28, 'DS', 'Ciro Lauro', 'T.I. - P.T. 66%', [('F29', 'p', None), ('J29', 'p', None)], None, '1700 quando fa meno di 13 turni')
    person(31, 'MED', 'Ciro Lauro', 'Dialisi', [('G31', 'm', None), ('I31', 'm', None), ('F32', 'p', None), ('J32', 'FE', None),
           ('F33', 's', None)], 'surplus')
    ws.write('A34', 'Medici Consulenti')
    person(35, 'MED', 'Elio Sarti', 'FATTURA', [('G35', 'm', None)])
    if extra_person:
        person(38, 'INF', extra_person, 'T.I.-FULL TIME', [('F38', 'm', None)], 'ccnl')
    for base in (40, 50):
        for offset, label in enumerate(('Pazienti turno mattina', 'Pazienti turno mattina Contumacia', 'Pazienti turno pomeriggio',
                                        'Pazienti turno pomeriggio Contumacia', 'Pazienti turno serale', 'Pazienti turno serale Contumacia')):
            r = base + offset
            ws.write(f'A{r}', label)
            if 'Contumacia' in label:
                if label.startswith('Pazienti turno mattina'):
                    ws.write_number(f'D{r}', 1)
                continue
            for d in range(1, patients_days + 1):
                col = ''
                i = d + 3
                while i:
                    i, rem = divmod(i - 1, 26)
                    col = chr(65 + rem) + col
                ws.write_number(f'{col}{r}', 10 + offset // 2 + (1 if base == 50 and d == 1 and offset == 0 else 0))
    ws.write('B180', 'Festività')
    for i, serial in enumerate((44927, 44932, 45033, 45034, 45041, 45047, 45079, 45153, 45231, 45268, 45285)):
        ws.write_number(f'B{181 + i}', serial)  # festività del 2023: anno diverso dal mese
    co = wb.add_worksheet('Collaboratori')
    co.write('A1', 'CENTRO:'); co.write_formula('C1', "'Da Compilare'!C6", None, center)
    for col, text in zip('ABCEFGHIJ', ('QUALIFICA', 'COLLABORATORE', 'TURNI   FERIALI/ FESTIVI', 'IMPORTO LORDO', "RITENUTA D'ACCONTO",
                                      'Cont. ENPAPI 4%', 'IMPORTO  NETTO', 'NOTE', 'IBAN')):
        co.write(f'{col}5', text)
    co.write('A6', 'INF'); co.write('B6', 'Nora  Fiume'); co.write_number('C6', 16); co.write_number('D6', 5)
    co.write_number('E6', 1437.5); co.write_number('H6', 1437.5); co.write('I6', '2 D'); co.write('J6', 'IBAN: IT00X0000000000000000000000')
    co.write('A7', 'MED'); co.write('B7', 'Zoe Lago'); co.write_number('C7', 14); co.write_number('D7', 2)
    co.write_number('E7', 1980); co.write_number('F7', 396); co.write_number('H7', 1584); co.write('J7', 'IBAN: IT00Y0000000000000000000000')
    co.write('A8', 'Totale prestazioni con fattura'); co.write_formula('E8', 'SUM(E6:E7)', None, 3417.5)
    wb.close()
    return stream.getvalue()


class ExcelImport(PortalCase):
    def upload(self, data):
        self.portal.step_up(self.admin)
        return self.admin.request('POST', '/api/import/preview', raw=data, content_type='application/octet-stream')

    def test_preview_then_confirm_once(self):
        workbook = sodav_workbook()  # lo stesso file due volte (il file contiene l'ora di creazione)
        preview = self.upload(workbook)
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
        again = self.upload(workbook)
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


class RealModelImport(PortalCase):
    """Il modello compilato davvero dagli uffici: celle fuori standard, sezioni, pazienti, collaboratori."""

    def upload(self, data):
        self.portal.step_up(self.admin)
        response = self.admin.request('POST', '/api/import/preview', raw=data, content_type='application/octet-stream')
        self.assertEqual(response.status, 200, response.body)
        return response.data

    def confirm(self, key, target=None):
        self.portal.step_up(self.admin)
        return self.admin.ok('POST', '/api/import/confirm', {'key': key, 'target': target})

    def test_preview_reports_everything_without_blocking(self):
        data = self.upload(real_like_workbook())
        self.assertEqual((data['center'], data['month'], data['people'], data['entries']), ('Centro Agosto Prova', '2026-08', 7, 19))
        self.assertEqual((data['external'], data['holiday_entries'], data['proposals'], data['skipped_total']), (1, 1, 4, 4))
        self.assertEqual(data['groups'], {'dipendente': 4, 'consulente': 3, '': 0})
        reasons = {s['cell']: s['reason'] for s in data['skipped']}
        self.assertIn('causale non riconosciuta', reasons['J11'])
        self.assertIn('formula', reasons['K11'])
        self.assertIn('Pomeriggio', reasons['H12'])
        self.assertIn('doppione', reasons['J32'])
        self.assertEqual(data['workload_days'], 5)
        self.assertEqual(data['parameters'], {'nurse_reference': 5.0, 'doctor_reference': 20.0, 'stations': 10, 'isolation_stations': 1})
        self.assertIn('2026-08-15', data['holidays'])
        self.assertFalse(any(h.startswith('2023') for h in data['holidays']))
        text = ' '.join(data['warnings'])
        for expected in ('festività di altri anni (2023)', 'X3 contiene 26', 'risultano 25', 'compare due volte', '4 celle non importate',
                         'Zoe Lago', 'non coincide con le tariffe'):
            self.assertIn(expected, text)
        persons = {p['name']: p for p in data['persons']}
        self.assertEqual(persons['Nora Fiume']['contract'], 'Prestazione / consulenza')
        self.assertEqual(persons['Nora Fiume']['billing'], 'FATTURA')
        self.assertEqual(persons['Pia Monti']['group'], 'Personale dipendente')
        self.assertEqual(persons['Ciro Lauro']['rows'], [28, 31])
        self.assertIn('16 turni feriali', persons['Nora Fiume']['collaborator'])
        self.assertNotIn('IT00', str(data))  # i codici IBAN del foglio Collaboratori non escono mai dal file
        self.assertEqual(data['targets'], [])

    def test_confirm_new_center_with_parameters_workload_and_proposals(self):
        data = self.upload(real_like_workbook())
        done = self.confirm(data['key'])
        self.assertEqual((done['people'], done['new_people'], done['skipped']), (7, 0, 4))
        cid = done['center_id']
        snap = self.admin.ok('GET', f'/api/attendance/{cid}/2026-08')
        self.assertEqual(len(snap['entries']), 19)
        self.assertEqual(sum(e['review'] == 'Registrazione presente due volte nel file con codici diversi: verificare.' for e in snap['entries']), 1)
        self.assertEqual(sum(e['site'] != '' for e in snap['entries']), 1)
        self.assertEqual(len(snap['workload']), 15)
        first = next(w for w in snap['workload'] if w['day'] == '2026-08-01' and w['slot'] == 'm')
        self.assertEqual((first['ordinary'], first['isolated']), (10, 1))
        self.assertIn('J11', snap['state']['note'])
        cfg = self.admin.ok('GET', f'/api/centers/{cid}/config')['config']
        self.assertEqual((cfg['nurse_reference'], cfg['doctor_reference']), (5, 20))
        self.assertIn('2026-08-15', cfg['holidays'])
        for role in ('INF', 'AMM', 'AUT', 'DS', 'MED'):
            self.assertIn(role, cfg['roles'])
        self.assertIn('Posti dialisi accreditati indicati nel file: 10', cfg['note'])
        persons = {p['name']: p for p in self.admin.ok('GET', f'/api/centers/{cid}/people')['people']}
        self.assertEqual(len(persons), 7)
        self.assertIn('Altri ruoli nel file: MED', persons['Ciro Lauro']['note'])
        self.assertIn('Fatturazione / ente indicato nel file: FATTURA', persons['Nora Fiume']['note'])
        self.assertIn('lordo 1.437,50', persons['Nora Fiume']['note'])
        self.assertNotIn('IT00', ' '.join(p['note'] for p in persons.values()))
        rows = {r['name']: r for r in self.admin.ok('GET', f'/api/agreements/{cid}/2026-08')['rows']}
        rosa = rows['Rosa Gialli']['agreement']
        self.assertEqual((rosa['basis'], rosa['ccnl_rate'], rosa['ccnl_count'], rosa['fixed_deduction'], rosa['confirmed']),
                         ('surplus', 70, 1, 100, False))
        self.assertEqual(rows['Dario Verdi']['agreement']['ccnl_count'], 0)
        self.assertEqual(rows['Nora Fiume']['agreement']['basis'], 'all')
        self.assertIn('lordo diverso dalle tariffe', rows['Nora Fiume']['source'])
        self.assertEqual(rows['Ciro Lauro']['agreement']['fixed_deduction'], 100)
        self.assertFalse(rows['Elio Sarti']['saved'])

    def test_following_month_joins_the_existing_center(self):
        first = self.upload(real_like_workbook())
        cid = self.confirm(first['key'])['center_id']
        september = self.upload(real_like_workbook(month_serial=46266, extra_person='Ivo Neri'))
        self.assertEqual(september['month'], '2026-09')
        self.assertEqual([(t['id'], t['importable']) for t in september['targets']], [(cid, True)])
        done = self.confirm(september['key'], cid)
        self.assertEqual((done['center_id'], done['people'], done['new_people']), (cid, 8, 1))
        people = self.admin.ok('GET', f'/api/centers/{cid}/people')['people']
        self.assertEqual(len(people), 8)
        snap = self.admin.ok('GET', f'/api/attendance/{cid}/2026-09')
        self.assertEqual(len(snap['entries']), 20)
        self.assertEqual(len(self.admin.ok('GET', '/api/centers')['centers']), 1)  # nessuna struttura doppia
        # Lo stesso mese con un altro file: la struttura esistente non è più una destinazione possibile.
        again = self.upload(real_like_workbook(month_serial=46266, note='seconda versione'))
        self.assertEqual([(t['importable'], t['reason']) for t in again['targets']], [(False, 'il mese contiene già registrazioni')])
        self.portal.step_up(self.admin)
        response = self.admin.post('/api/import/confirm', {'key': again['key'], 'target': cid})
        self.assertStatus(response, 400, 'contiene già registrazioni')

    def test_target_must_be_a_known_center(self):
        data = self.upload(real_like_workbook())
        self.portal.step_up(self.admin)
        self.assertStatus(self.admin.post('/api/import/confirm', {'key': data['key'], 'target': 'non-esiste'}), 404)
        self.portal.step_up(self.admin)
        self.assertStatus(self.admin.post('/api/import/confirm', {'key': data['key'], 'target': 5}), 400, 'destinazione')


if __name__ == '__main__':
    unittest.main()
