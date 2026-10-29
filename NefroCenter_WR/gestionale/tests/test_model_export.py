"""Foglio mensile nel formato del vecchio modello Excel: contenuto, colori, permessi e storico.

Il file viene letto con zipfile e xml.etree (nessuna libreria esterna): stringhe condivise, celle per foglio,
stili delle celle (riempimenti e caratteri) per controllare il giallo del fuori sede e il rosso del festivo.
"""
import io
import re
import unittest
import zipfile
import xml.etree.ElementTree as ET

from test_attendance import MONTH, AttendanceCase

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def column_index(ref):
    letters = re.match(r'[A-Z]+', ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


class Book:
    """Lettura minima di un file .xlsx: nomi dei fogli, celle con valore e stile, colori degli stili."""

    def __init__(self, data):
        self.zip = zipfile.ZipFile(io.BytesIO(data))
        wb = ET.fromstring(self.zip.read('xl/workbook.xml'))
        rels = {rel.get('Id'): rel.get('Target') for rel in ET.fromstring(self.zip.read('xl/_rels/workbook.xml.rels'))}
        self.sheets = {}
        for s in wb.find('m:sheets', NS):
            target = rels[s.get('{%s}id' % NS['r'])]
            self.sheets[s.get('name')] = 'xl/' + target.lstrip('/').replace('xl/', '')
        self.names = list(self.sheets)
        self.strings = []
        if 'xl/sharedStrings.xml' in self.zip.namelist():
            for si in ET.fromstring(self.zip.read('xl/sharedStrings.xml')).findall('m:si', NS):
                self.strings.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
        styles = ET.fromstring(self.zip.read('xl/styles.xml'))
        self.fills, self.fonts = [], []
        for fill in styles.find('m:fills', NS):
            fg = fill.find('m:patternFill/m:fgColor', NS)
            self.fills.append((fg.get('rgb') or '') if fg is not None else '')
        for font in styles.find('m:fonts', NS):
            color = font.find('m:color', NS)
            self.fonts.append((color.get('rgb') or '') if color is not None else '')
        self.xfs = [(int(xf.get('fillId', 0)), int(xf.get('fontId', 0))) for xf in styles.find('m:cellXfs', NS)]

    def grid(self, name):
        """{(riga, colonna): (valore, indice di stile)} con indici a partire da 0."""
        out = {}
        root = ET.fromstring(self.zip.read(self.sheets[name]))
        for c in root.iter('{%s}c' % NS['m']):
            ref = c.get('r')
            row = int(re.search(r'\d+', ref).group(0)) - 1
            col = column_index(ref)
            v = c.find('m:v', NS)
            value = None
            if v is not None:
                value = self.strings[int(v.text)] if c.get('t') == 's' else float(v.text)
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
            out[row, col] = (value, int(c.get('s', 0)))
        return out

    def fill_of(self, style):
        return self.fills[self.xfs[style][0]]

    def font_color_of(self, style):
        return self.fonts[self.xfs[style][1]]


class Sheet:
    def __init__(self, book, name):
        self.cells = book.grid(name)
        self.book = book

    def value(self, row, col):
        return self.cells.get((row, col), (None, 0))[0]

    def style(self, row, col):
        return self.cells.get((row, col), (None, 0))[1]

    def values(self):
        return [v for v, _ in self.cells.values() if v is not None]

    def find_row(self, text, col=None):
        """Prima riga che contiene il testo (in una colonna precisa o in qualsiasi colonna)."""
        for (r, c), (v, _) in sorted(self.cells.items()):
            if v == text and (col is None or c == col):
                return r
        raise AssertionError(f'Testo non trovato nel foglio: {text!r}')

    def columns(self, row):
        """{testo: colonna} per una riga di intestazione."""
        return {v: c for (r, c), (v, _) in self.cells.items() if r == row and isinstance(v, str)}


class ModelExport(AttendanceCase):
    """Un mese di prova: turno fuori sede, turno festivo, assenze, pazienti per fascia e due accordi confermati."""

    def setUp(self):
        super().setUp()
        self.hr = self.portal.user('hrcentrale', 'hr')
        self.assertEqual(self.save_config(lambda c: c.update(sites=['Altra sede'])).status, 200)
        for day in ('2026-10-05', '2026-10-06', '2026-10-07'):
            self.assertEqual(self.entry(self.manager, day=day).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-08', site='Altra sede').status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-11', holiday=True).status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-12', code='FE').status, 200)
        self.assertEqual(self.entry(self.manager, day='2026-10-13', code='MA').status, 200)
        for day in ('2026-10-05', '2026-10-06', '2026-10-07'):
            self.assertEqual(self.entry(self.manager, day=day, person=self.luca).status, 200)
        self.manager.ok('PUT', f'/api/attendance/{self.cid}/{MONTH}/workload',
                        {'day': '2026-10-05', 'slot': 'm', 'ordinary': 8, 'isolated': 1})
        # Luca è un medico consulente con fattura: ritenuta 20 %, cassa 4 %, IBAN fittizio.
        detail = self.hr.ok('GET', f'/api/hr/{self.cid}/{self.luca}')
        fields = dict(detail['profile']['fields'], relationship='professionista', billing_entity='Studio medico di prova',
                      withholding_rate='20', fund_rate='4', iban='IT60X0542811101000000123456', account_holder='Luca Verdi')
        self.hr.ok('PUT', f'/api/hr/{self.cid}/{self.luca}', {'name': 'Luca Verdi', 'role': 'MED', 'registration': 'M002',
                                                              'stage': 'active', 'fields': fields, 'custom': {},
                                                              'version': detail['profile']['version']})
        for pid in (self.anna, self.luca):
            report = self.manager.ok('GET', f'/api/agreements/{self.cid}/{MONTH}')
            agreement = next(r for r in report['rows'] if r['person_id'] == pid)['agreement']
            agreement.update(basis='all', confirmed=True)
            self.portal.step_up(self.manager)
            self.manager.ok('PUT', f'/api/agreements/{self.cid}/{MONTH}/{pid}',
                            {'agreement': agreement, 'reason': 'Accordo di prova confermato', 'version': 0})
        self.report = self.manager.ok('GET', f'/api/agreements/{self.cid}/{MONTH}')

    def download(self, client):
        response = client.get(f'/api/exports/modello/{self.cid}/{MONTH}')
        self.assertEqual(response.status, 200, response.body[:300])
        self.assertTrue(response.body.startswith(b'PK'))
        return response

    def test_manager_file_has_all_sheets_grid_counters_office_and_indicators(self):
        response = self.download(self.manager)
        self.assertIn('Presenze_EST_2026-10.xlsx', response.header('Content-Disposition'))
        self.assertIn('attachment;', response.header('Content-Disposition'))
        book = Book(response.body)
        self.assertEqual(book.names, ['Registro', 'Per consulente', 'Collaboratori', 'Informazioni'])
        self.assertNotIn('xl/vbaProject.bin', book.zip.namelist())
        sheet = Sheet(book, 'Registro')
        values = sheet.values()
        self.assertIn('Anna Bianchi', values)
        self.assertIn('Luca Verdi', values)
        self.assertIn('Personale dipendente · infermieri', values)
        self.assertIn('Medici consulenti', values)
        self.assertIn('Totali personale', values)
        # Griglia: riga della fascia «m» di Anna; i giorni partono dalla colonna D (indice 3).
        name_row = sheet.find_row('Anna Bianchi', col=1)
        self.assertEqual(sheet.value(name_row, 2), 'm')
        self.assertEqual(sheet.value(name_row, 3 + 4), 'm')         # 5 ottobre
        self.assertEqual(sheet.value(name_row, 3 + 11), 'FE')       # 12 ottobre, assenza in maiuscolo
        self.assertEqual(sheet.value(name_row, 3 + 12), 'MA')
        external = sheet.style(name_row, 3 + 7)                    # 8 ottobre, fuori sede → sfondo giallo
        self.assertEqual(sheet.value(name_row, 3 + 7), 'm')
        self.assertTrue(book.fill_of(external).upper().endswith('FFFF00'), book.fill_of(external))
        festive = sheet.style(name_row, 3 + 10)                    # 11 ottobre, festivo → carattere rosso
        self.assertEqual(sheet.value(name_row, 3 + 10), 'm')
        self.assertTrue(book.font_color_of(festive).upper().endswith('FF0000'), book.font_color_of(festive))
        self.assertFalse(book.font_color_of(external).upper().endswith('FF0000'))
        # Contatori: la riga di intestazione contiene «Turni»; i contatori stanno sulla prima riga del blocco.
        head = sheet.find_row('Turni')
        cols = sheet.columns(head)
        self.assertEqual(sheet.value(name_row, cols['Turni']), 5)
        self.assertEqual(sheet.value(name_row, cols['FE']), 1)
        self.assertEqual(sheet.value(name_row, cols['MA']), 1)
        self.assertEqual(sheet.value(name_row, cols['PS']), 0)
        self.assertEqual(sheet.value(name_row, cols['Totale registrazioni']), 7)
        self.assertEqual(sheet.value(name_row, cols['Fuori sede']), 1)
        self.assertEqual(sheet.value(name_row, cols['Festivi']), 1)
        # Spazio ufficio del personale: il Totale è l'importo dell'accordo confermato (6 feriali × 50 + 1 festivo × 70 − 100).
        anna = next(r for r in self.report['rows'] if r['person_id'] == self.anna)
        self.assertEqual(anna['amount'], 270.0)
        self.assertEqual(sheet.value(name_row, cols['Totale']), anna['amount'])
        self.assertEqual(sheet.value(name_row, cols['Giorni extra']), 7)
        self.assertEqual(sheet.value(name_row, cols['Feriali']), 6)
        self.assertEqual(sheet.value(name_row, cols['Netto feriale']), 300)
        self.assertEqual(sheet.value(name_row, cols['Netto festivo']), 70)
        self.assertEqual(sheet.value(name_row, cols['Festivi CCNL']), 0)
        self.assertIn('confermato', sheet.value(name_row, cols['Accordo']))
        # Totali personale: somma dei turni delle due persone (5 + 3).
        totals_row = sheet.find_row('Totali personale', col=0)
        self.assertEqual(sheet.value(totals_row, cols['Turni']), 8)
        self.assertEqual(sheet.value(totals_row, cols['Totale']), anna['amount'] + 50.0)
        # Indicatori: infermieri in turno nella sede (il turno fuori sede non conta), pazienti inseriti, rapporto ed efficienza.
        staff_row = sheet.find_row('Infermieri in turno Mattina', col=0)
        self.assertEqual(sheet.value(staff_row, 3 + 4), 1)
        self.assertEqual(sheet.value(staff_row, 3 + 7), 0)
        self.assertEqual(sheet.value(staff_row, cols['Turni']), 4)      # colonna «Totale mese»
        patients_row = sheet.find_row('Pazienti Mattina', col=0)
        self.assertEqual(sheet.value(patients_row, 3 + 4), 8)
        self.assertEqual(sheet.value(patients_row + 1, 3 + 4), 1)      # in isolamento
        ratio_row = sheet.find_row('Rapporto pazienti/infermiere Mattina', col=0)
        self.assertEqual(sheet.value(ratio_row, 3 + 4), 13)             # (8 + 1 × 5) / 1
        efficiency_row = sheet.find_row('Efficienza Mattina', col=0)
        self.assertEqual(sheet.value(efficiency_row, 3 + 4), 2.6)       # 13 / 5 → adeguata (verde)
        self.assertTrue(book.fill_of(sheet.style(efficiency_row, 3 + 4)).upper().endswith('D9EAD3'))
        doctor_ratio = sheet.find_row('Rapporto pazienti/medico Mattina', col=0)
        self.assertEqual(sheet.value(doctor_ratio, 3 + 4), 9)           # (8 + 1) / 1, senza peso
        self.assertEqual(sheet.value(doctor_ratio + 1, 3 + 4), 0.45)    # 9 / 20 → sotto la soglia (arancione)
        self.assertTrue(book.fill_of(sheet.style(doctor_ratio + 1, 3 + 4)).upper().endswith('FCE5CD'))
        # Totale mese della fascia: rapporto dai totali (8 + 1 × 5) / 4 turni in sede = 3.25, efficienza 3.25 / 5 = 0.65.
        self.assertEqual(sheet.value(ratio_row, cols['Turni']), 3.25)
        self.assertEqual(sheet.value(efficiency_row, cols['Turni']), 0.65)
        self.assertTrue(book.fill_of(sheet.style(efficiency_row, cols['Turni'])).upper().endswith('FCE5CD'))
        summary = sheet.find_row('Totale turni da lavorare', col=0)
        self.assertEqual(sheet.value(summary, cols['Turni']), 4)
        self.assertEqual(sheet.value(summary + 1, cols['Turni']), 9)    # dialisi: 8 + 1
        self.assertEqual(sheet.value(summary + 2, cols['Turni']), 3.25) # media dei rapporti mensili delle fasce con dati
        self.assertEqual(sheet.value(summary + 3, cols['Turni']), 0.65)
        # Parametri in testa e legenda.
        self.assertIn('Giorni lavorativi del mese', values)
        self.assertEqual(sheet.value(sheet.find_row('Giorni lavorativi del mese', col=0), 2), 27)
        self.assertTrue(any(isinstance(v, str) and 'FE = Ferie' in v for v in values))
        self.assertTrue(any(isinstance(v, str) and v.startswith('Sfondo giallo') for v in values))

    def test_consultant_and_collaborators_sheets(self):
        book = Book(self.download(self.manager).body)
        consultant = Sheet(book, 'Per consulente')
        values = consultant.values()
        self.assertTrue(any(isinstance(v, str) and 'elaborazione dei cedolini' in v for v in values))
        self.assertIn('Anna Bianchi', values)
        self.assertIn('Festivi CCNL', values)
        self.assertNotIn('Pazienti Mattina', values)
        self.assertFalse(any(isinstance(v, str) and v.startswith('Infermieri in turno') for v in values))
        head = consultant.find_row('Turni')
        cols = consultant.columns(head)
        row = consultant.find_row('Anna Bianchi', col=1)
        self.assertEqual(consultant.value(row, cols['Totale']), 270.0)
        collab = Sheet(book, 'Collaboratori')
        head = collab.find_row('Collaboratore')
        cols = collab.columns(head)
        self.assertIn('IBAN', cols)
        row = collab.find_row('Luca Verdi', col=cols['Collaboratore'])
        self.assertEqual(collab.value(row, cols['Gruppo']), 'Collaboratore con fattura (libero professionista)')
        self.assertEqual(collab.value(row, cols['Chi fattura']), 'Studio medico di prova')
        self.assertEqual(collab.value(row, cols['Turni feriali']), 3)
        self.assertEqual(collab.value(row, cols['Lordo']), 50.0)             # 3 × 50 − 100
        self.assertEqual(collab.value(row, cols['Ritenuta d’acconto']), 10.0)
        self.assertEqual(collab.value(row, cols['Contributo cassa']), 2.0)
        self.assertEqual(collab.value(row, cols['Netto']), 42.0)
        self.assertEqual(collab.value(row, cols['IBAN']), 'IT60X0542811101000000123456')
        self.assertEqual(collab.value(row, cols['Intestatario']), 'Luca Verdi')
        total = collab.find_row('Totale complessivo', col=0)
        self.assertEqual(collab.value(total, cols['Netto']), 42.0)
        self.assertNotIn('Anna Bianchi', collab.values(), 'i dipendenti non compaiono fra i collaboratori')
        info = Sheet(book, 'Informazioni')
        self.assertIn('Stato del mese', info.values())
        self.assertTrue(any(isinstance(v, str) and 'non tornano nel portale' in v for v in info.values()))

    def test_operator_file_has_no_economic_parts_and_download_is_recorded(self):
        response = self.download(self.operator)
        book = Book(response.body)
        self.assertEqual(book.names, ['Registro', 'Informazioni'])
        sheet = Sheet(book, 'Registro')
        values = sheet.values()
        self.assertIn('Anna Bianchi', values)
        self.assertIn('Luca Verdi', values)
        self.assertIn('Turni', values)
        for forbidden in ('Netto feriale', 'Totale', 'Festivi CCNL', 'Spazio riservato ufficio del personale', 'Pazienti Mattina'):
            self.assertNotIn(forbidden, values)
        name_row = sheet.find_row('Anna Bianchi', col=1)
        self.assertTrue(book.fill_of(sheet.style(name_row, 3 + 7)).upper().endswith('FFFF00'))
        history = self.snap(self.operator)['history']
        self.assertTrue(any(h['action'] == 'Esportazione Excel: foglio mensile' and h['actor'] == 'compilatore' for h in history))
        with self.portal.db.read() as con:
            rows = con.execute("SELECT entity, entity_id, after FROM audit WHERE action='Esportazione Excel: foglio mensile'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['entity'], rows[0]['entity_id']), ('export', 'modello'))
        self.assertIn(MONTH, rows[0]['after'])

    def test_scope_and_validation(self):
        other = self.portal.center('Centro Ovest', 'OVEST')
        self.assertStatus(self.operator.get(f'/api/exports/modello/{other}/{MONTH}'), 403, 'non assegnata')
        self.assertStatus(self.manager.get(f'/api/exports/modello/{self.cid}/2026-13'), 400)
        viewer = self.portal.user('direzione', 'viewer', [self.cid])
        book = Book(self.download(viewer).body)
        self.assertEqual(book.names, ['Registro', 'Informazioni'])
        empty = Book(self.manager.get(f'/api/exports/modello/{self.cid}/2026-11').body)
        self.assertEqual(empty.names, ['Registro', 'Per consulente', 'Collaboratori', 'Informazioni'])
        sheet = Sheet(empty, 'Registro')
        self.assertIn('Anna Bianchi', sheet.values(), 'le persone attive compaiono anche in un mese vuoto')


if __name__ == '__main__':
    unittest.main()
