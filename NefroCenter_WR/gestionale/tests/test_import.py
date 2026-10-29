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
        self.assertEqual((data['external'], data['holiday_entries'], data['proposals'], data['skipped_total']), (1, 1, 4, 5))
        self.assertEqual(data['groups'], {'dipendente': 4, 'consulente': 3, '': 0})
        reasons = {s['cell']: s['reason'] for s in data['skipped']}
        self.assertIn('causale non riconosciuta', reasons['J11'])
        self.assertIn('formula', reasons['K11'])
        self.assertIn('Pomeriggio', reasons['H12'])
        self.assertIn('doppione con codice diverso', reasons['J32'])
        self.assertIn('doppione dello stesso turno', reasons['F32'])
        self.assertEqual(data['workload_days'], 5)
        self.assertEqual(data['parameters'], {'nurse_reference': 5.0, 'doctor_reference': 20.0, 'stations': 10, 'isolation_stations': 1})
        self.assertIn('2026-08-15', data['holidays'])
        self.assertFalse(any(h.startswith('2023') for h in data['holidays']))
        text = ' '.join(data['warnings'])
        for expected in ('festività di altri anni (2023)', 'X3 contiene 26', 'risultano 25', 'compare due volte', '5 celle non importate',
                         'Zoe Lago', 'non coincide con le tariffe', 'la proposta economica deriva dalle sole righe 31-33'):
            self.assertIn(expected, text)
        persons = {p['name']: p for p in data['persons']}
        self.assertEqual(persons['Nora Fiume']['contract'], 'Prestazione / consulenza')
        self.assertEqual(persons['Nora Fiume']['billing'], 'FATTURA')
        self.assertEqual(persons['Pia Monti']['group'], 'Personale dipendente')
        self.assertEqual(persons['Ciro Lauro']['rows'], [28, 31])
        self.assertIn('16 turni feriali', persons['Nora Fiume']['collaborator'])
        self.assertNotIn('IT00', str(data))  # i codici IBAN del foglio Collaboratori non escono mai dal file
        self.assertEqual(data['targets'], [])
        self.assertIsNone(data['already_imported'])
        self.assertEqual(data['blocking'], [])
        self.assertTrue(any('senza orari' in n for n in data['notes']))

    def test_confirm_new_center_with_parameters_workload_and_proposals(self):
        data = self.upload(real_like_workbook())
        done = self.confirm(data['key'])
        self.assertEqual((done['people'], done['new_people'], done['skipped']), (7, 0, 5))
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
        self.assertIn('Contratto o fatturazione negli altri blocchi: Dialisi', persons['Ciro Lauro']['note'])
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
        self.assertIn('riga 31', rows['Ciro Lauro']['source'])
        self.assertIn('X3 = 26', rows['Rosa Gialli']['source'])
        self.assertEqual(cfg['dialysis_stations'], 10)
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
        self.assertEqual(again['already_imported'], None)
        repeat = self.upload(real_like_workbook(month_serial=46266, extra_person='Ivo Neri'))
        self.assertEqual(repeat['already_imported']['center_id'], cid)
        self.portal.step_up(self.admin)
        response = self.admin.post('/api/import/confirm', {'key': again['key'], 'target': cid})
        self.assertStatus(response, 400, 'contiene già registrazioni')

    def test_target_must_be_a_known_center(self):
        data = self.upload(real_like_workbook())
        self.portal.step_up(self.admin)
        self.assertStatus(self.admin.post('/api/import/confirm', {'key': data['key'], 'target': 'non-esiste'}), 404)
        self.portal.step_up(self.admin)
        self.assertStatus(self.admin.post('/api/import/confirm', {'key': data['key'], 'target': 5}), 400, 'destinazione')


def tiny_xlsx(sheet_xml, strings=(), styles=None, extra_files=None, sheet_name='Da Compilare'):
    """Cartella di lavoro minima scritta a mano: serve a provare parser e casi ostili senza librerie esterne."""
    import zipfile
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    files = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        'xl/workbook.xml': f'<?xml version="1.0" encoding="UTF-8"?><workbook {ns}><sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/><Relationship Id="rId9" Type="x" TargetMode="External" Target="http://esempio.invalid/"/>'
                                      '<Relationship Id="rId8" Type="x"/></Relationships>',
        'xl/worksheets/sheet1.xml': f'<?xml version="1.0" encoding="UTF-8"?><worksheet {ns}><sheetData>{sheet_xml}</sheetData></worksheet>',
        'xl/sharedStrings.xml': f'<?xml version="1.0" encoding="UTF-8"?><sst {ns}>' + ''.join(f'<si><t>{t}</t></si>' for t in strings) + '</sst>',
        'xl/styles.xml': styles or f'<?xml version="1.0" encoding="UTF-8"?><styleSheet {ns}><fonts><font/></fonts><fills><fill><patternFill patternType="none"/></fill></fills><cellXfs><xf fontId="0" fillId="0"/></cellXfs></styleSheet>',
    }
    files.update(extra_files or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return stream.getvalue()


def cell(addr, value=None, text=None, formula=None, shared=None):
    attrs = f' r="{addr}"'
    if text is not None:
        return f'<c{attrs} t="inlineStr"><is><t>{text}</t></is></c>'
    inner = ''
    if formula is not None or shared is not None:
        if shared is not None and formula is None:
            inner += f'<f t="shared" si="{shared}"/>'
        elif shared is not None:
            inner += f'<f t="shared" si="{shared}" ref="A1">{formula}</f>'
        else:
            inner += f'<f>{formula}</f>'
    if value is not None:
        inner += f'<v>{value}</v>'
    return f'<c{attrs}>{inner}</c>'


def minimal_model(extra_cells='', person_rows=(10,), with_shared=False):
    """Un modello con intestazione minima (C6 struttura, O6 mese) e un blocco persona per ogni riga indicata."""
    rows = [cell('C6', text='Centro Minimo'), cell('O6', 46054)]
    for r in person_rows:
        rows += [cell(f'A{r}', text='INF'), cell(f'B{r}', text=f'Persona {r}'), cell(f'C{r}', text='m'), cell(f'C{r + 1}', text='p'),
                 cell(f'C{r + 2}', text='s'), cell(f'D{r}', text='m'), cell(f'E{r + 1}', text='p')]
        if with_shared:
            end = r + 2
            rows += [cell(f'AT{r}', 2, formula=f'93-COUNTBLANK(D{r}:AH{end})')]
            if r == person_rows[0]:
                rows += [cell(f'AV{end}', '', formula=f'AT{r}', shared=0), cell(f'AW{end}', '', formula=f'IF(AV{end}="","",AV{end}-AY{end})', shared=1),
                         cell(f'AX{end}', '', formula=f'IF(AW{end}="","",AW{end}*50)', shared=2), cell(f'AZ{end}', '', formula=f'IF(AY{end}="","",AY{end}*70)', shared=3),
                         cell(f'BA{end}', '', formula=f'IF(AX{end}="","",AX{end}+AZ{end})', shared=4)]
            else:
                rows += [cell(f'AV{end}', '', shared=0), cell(f'AW{end}', '', shared=1), cell(f'AX{end}', '', shared=2),
                         cell(f'AZ{end}', '', shared=3), cell(f'BA{end}', '', shared=4)]
    body = ''.join(f'<row r="{n}">{c}</row>' for n, c in enumerate(rows, start=1))  # l'ordine delle righe non conta per il lettore
    return tiny_xlsx(body + extra_cells)


class HostileAndOddFiles(PortalCase):
    """File ostili o fuori standard: mai un errore 500, mai una perdita silenziosa."""

    def read(self, data):
        from wr import excel_import
        return excel_import.read_model(data)

    def rejected(self, data, text):
        from wr.errors import Invalid
        with self.assertRaises(Invalid) as ctx:
            self.read(data)
        self.assertIn(text, ctx.exception.message)

    def test_minimal_model_and_shared_formulas(self):
        model = self.read(minimal_model(person_rows=(10, 13), with_shared=True))
        self.assertEqual((model['center'], model['month'], len(model['people']), len(model['entries'])), ('Centro Minimo', '2026-02', 2, 4))
        self.assertEqual([p['proposal']['basis'] for p in model['people']], ['all', 'all'])
        self.assertEqual(model['people'][1]['proposal']['weekday_rate'], 50)
        from wr.excel_import import shift_formula
        self.assertEqual(shift_formula('IF(AT10<=0,"",AT10-$X$3)', 'AV12', 'AV15'), 'IF(AT13<=0,"",AT13-$X$3)')
        self.assertEqual(shift_formula('COUNTIF(D10:AH12,"FE")', 'AJ10', 'AJ13'), 'COUNTIF(D13:AH15,"FE")')

    def test_blocks_without_name_or_with_broken_column_c_are_listed(self):
        extra = ''.join([cell('C20', text='m'), cell('C21', text='p'), cell('C22', text='s'), cell('D20', text='m'), cell('F21', text='FE'), cell('B21', text='Nome Spostato'),
                         cell('A30', text='MED'), cell('B30', text='Senza Terna'), cell('C30', text='m'), cell('C31', text='p'), cell('D30', text='m'), cell('G30', text='MA')])
        model = self.read(minimal_model('<row r="60">' + extra + '</row>'))
        reasons = {s['cell']: s['reason'] for s in model['skipped']}
        self.assertEqual(reasons['D20'], 'blocco senza nominativo')
        self.assertEqual(reasons['F21'], 'blocco senza nominativo')
        self.assertIn('colonna C incompleta', reasons['D30'])
        self.assertIn('colonna C incompleta', reasons['G30'])
        text = ' '.join(model['warnings'])
        self.assertIn('Blocco alle righe 20-22 senza nominativo', text)
        self.assertIn('Nome Spostato', text)
        self.assertIn('Blocco non riconosciuto alla riga 30', text)
        self.assertEqual(len(model['people']), 1)

    def test_hostile_files_are_refused_cleanly(self):
        self.rejected(b'PK\x03\x04 non uno zip valido', 'cartella di lavoro')
        doctype = tiny_xlsx('', extra_files={'xl/sharedStrings.xml': '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><sst><si><t>&a;</t></si></sst>'})
        self.rejected(doctype, 'entità')
        utf16 = tiny_xlsx('', extra_files={'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-16"?><workbook/>'.encode('utf-16')})
        self.rejected(utf16, 'Codifica')
        broken = tiny_xlsx('', extra_files={'xl/workbook.xml': '<workbook><sheets><sheet'})
        self.rejected(broken, 'Struttura')
        no_o6 = tiny_xlsx(cell('C6', text='Centro'))
        self.rejected(no_o6, 'O6')
        far_future = tiny_xlsx(cell('C6', text='Centro') + cell('O6', 2958465))  # anno 9999
        self.rejected(far_future, 'anno tra il 2000 e il 2100')
        wrong_sheet = tiny_xlsx(cell('C6', text='Centro') + cell('O6', 46054), sheet_name='Altro')
        self.rejected(wrong_sheet, 'Da Compilare')

    def test_odd_cells_do_not_crash(self):
        odd = '<row r="1">' + ''.join([
            '<c><v>1</v></c>', '<c r="ZZZZ1"><v>1</v></c>', '<c r="A7" s="abc" t="s"><v>9999</v></c>',
            cell('AJ4', 'nan'), cell('AM4', '1e400'), cell('AD4', 'inf'),
            cell('A40', text='Pazienti turno mattina'), cell('D40', '1e400'), cell('E40', '12'), cell('F40', 'nan'),
            cell('B180', text='Festività'), cell('B181', 46071), cell('B182', '1e400'), cell('B183', 'xyz'), cell('B184', 46072),
            cell('X3', 26, formula='NETWORKDAYS.INTL(O6,O6+27,11,B1:B1048576)')]) + '</row>'
        model = self.read(minimal_model(odd))
        self.assertEqual(model['parameters'], {})
        self.assertEqual(model['workload'], [dict(day='2026-02-02', slot='m', ordinary=12, isolated=0)])
        self.assertIn('2026-02-18', model['holidays'])
        self.assertNotIn('2026-02-19', model['holidays'], 'un testo interrompe l’elenco delle festività')
        self.assertTrue(any('non leggibili o fuori misura' in w for w in model['warnings']))


class TargetChecks(PortalCase):
    """Importazione in una struttura esistente: ogni impedimento è noto già in anteprima, prima del backup."""

    def upload(self, data):
        self.portal.step_up(self.admin)
        response = self.admin.request('POST', '/api/import/preview', raw=data, content_type='application/octet-stream')
        self.assertEqual(response.status, 200, response.body)
        return response.data

    def confirm(self, key, target=None):
        self.portal.step_up(self.admin)
        return self.admin.post('/api/import/confirm', {'key': key, 'target': target})

    def test_same_name_required_and_inactive_homonym_blocks(self):
        other = self.portal.center('Altra Struttura', 'ALTRA')
        data = self.upload(real_like_workbook())
        self.assertStatus(self.confirm(data['key'], other), 400, 'stesso nome')
        same = self.portal.center('Centro Agosto Prova', 'STESSO')
        current = self.admin.ok('GET', f'/api/centers/{same}/config')
        cfg = dict(current['config'], sites=['Sede esterna da specificare'])
        self.portal.step_up(self.admin)
        self.admin.ok('PUT', f'/api/centers/{same}/config', {'config': cfg, 'version': current['version'], 'note': 'Sede esterna'})
        pid = self.admin.ok('POST', f'/api/centers/{same}/people', {'name': 'Rosa Gialli', 'role': 'INF', 'registration': 'R1'})['id']
        person = self.admin.ok('GET', f'/api/centers/{same}/people')['people'][0]
        self.admin.ok('PUT', f'/api/centers/{same}/people/{pid}', {'active': False, 'version': person['version']})
        data = self.upload(real_like_workbook())
        self.assertEqual([(t['importable'], t['reason'].startswith('persone disattivate con lo stesso nome')) for t in data['targets']], [(False, True)])
        self.assertStatus(self.confirm(data['key'], same), 400, 'disattivate')
        backups_before = self.admin.ok('GET', '/api/backups')['count']
        self.assertStatus(self.confirm(data['key'], same), 400, 'disattivate')
        self.assertEqual(self.admin.ok('GET', '/api/backups')['count'], backups_before, 'nessun backup per una conferma rifiutata')

    def test_missing_codes_and_existing_workload_are_reasons(self):
        same = self.portal.center('Centro Agosto Prova', 'STESSO')
        current = self.admin.ok('GET', f'/api/centers/{same}/config')
        cfg = current['config']
        cfg['codes'] = [c for c in cfg['codes'] if c['id'] != 'FE']
        self.portal.step_up(self.admin)
        self.admin.ok('PUT', f'/api/centers/{same}/config', {'config': cfg, 'version': current['version'], 'note': 'Senza ferie'})
        data = self.upload(real_like_workbook())
        self.assertEqual(data['targets'][0]['reason'], 'mancano le causali FE nei parametri')
        cfg = self.admin.ok('GET', f'/api/centers/{same}/config')['config']
        cfg['codes'].append(dict(id='FE', label='Ferie', kind='absence', credit_minutes=0, color='#3f8f7a', active=True, allowed_slots=[]))
        self.portal.step_up(self.admin)
        self.admin.ok('PUT', f'/api/centers/{same}/config', {'config': cfg, 'version': 2, 'note': 'Con ferie'})
        self.admin.ok('PUT', f'/api/attendance/{same}/2026-08/workload', {'day': '2026-08-03', 'slot': 'm', 'ordinary': 5, 'isolated': 0})
        data = self.upload(real_like_workbook())
        self.assertEqual(data['targets'][0]['reason'], 'il mese contiene già pazienti per fascia')


if __name__ == '__main__':
    unittest.main()
