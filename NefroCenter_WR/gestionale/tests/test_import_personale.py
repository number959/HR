"""Importazione del database del personale (strumenti/importa_personale.py) con una cartella Excel fittizia."""
import io
import sys
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401
from support import PortalCase
from wr import users

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'strumenti'))
import importa_personale as imp  # noqa: E402

HEADERS = ["SOCIETA'", 'REGIONE', 'PROVINCIA', "CITTA'", 'INDIRIZZO', "TIPOLOGIA ATTIVITA'", 'CODICE ATECO', 'LIVELLO RISCHIO',
           'REFERENTE', 'LUOGO DI LAVORO', 'NOMINATIVO', 'SESSO', 'DATA DI NASCITA', 'CODICE FISCALE', 'E-MAIL',
           'TIPOLOGIA CONTRATTO', '% PART TIME', 'CCNL', 'LIVELLO CONTRATTUALE', 'MANSIONE', 'ORE CONTRATTO h/w',
           'DATA INIZIO GG/MM/AA', 'DATA FINE GG/MM/AA', 'STATO CONTRATTO', 'DATA VISITA Idoneità sanitaria',
           'SCADENZA Idoneità sanitaria', 'SCADENZA ANTINCENDIO', 'MEDICO COMPETENTE']
# Dati fittizi: codici fiscali costruiti come esempio, non reali.
ROWS = [
    ['CENTRO DIALISI EST SCARL', 'CAMPANIA', 'NA', 'NAPOLI', 'Via Prova 1', 'DIALISI', '86.22.09', 'ALTO', 'Rossi', '',
     'Bianchi Anna', 'F', '1980-05-04', 'BNCNNA80E44F839X', 'anna.bianchi@esempio.it', 'DIPENDENTE FT', '', 'AIOP PERS. NON MEDICO',
     'D2', 'Infermiere/a', 36, '2020-01-01', '', 'IN CORSO', '2026-02-10', '2027-02-09', '2028-02-09', 'Verdi'],
    ['CENTRO DIALISI EST SCARL', 'CAMPANIA', 'NA', 'NAPOLI', 'Via Prova 1', 'DIALISI', '86.22.09', 'ALTO', 'Rossi', 'SALERNO',
     'Di Maio Luca', 'M', '1975-11-20', '', 'non-una-email', 'DIPENDENTE PT', 0.5, 'AIOP PERS. NON MEDICO', 'C1',
     'OSS', 18, '2018-03-01', '', 'IN CORSO', 'DA FARE', 'DA FARE', '', 'Verdi'],
    ['CENTRO DIALISI EST SCARL', 'CAMPANIA', 'NA', 'NAPOLI', 'Via Prova 1', 'DIALISI', '86.22.09', 'ALTO', 'Rossi', '',
     'Bianchi Anna', 'F', '1980-05-04', 'BNCNNA80E44F839X', '', 'DIPENDENTE PT', 0.5, 'AIOP PERS. NON MEDICO',
     'D1', 'Infermiere/a', 18, '2015-06-01', '2019-12-31', 'TERMINATO', '', '', '', ''],
    ['SERVIZI PULIZIE SRL', 'LAZIO', 'RM', 'ROMA', 'Via Prova 2', 'PULIZIE - OSA', '81.21', 'BASSO', 'Neri', 'ROMA',
     'Bianchi Anna', 'F', '1980-05-04', 'BNCNNA80E44F839X', '', 'COLL. OCC.', '', 'COMMERCIO', '',
     'Add. alle pulizie', 0, '2024-01-01', '', 'CONSULENZA ATTIVA', '', 'NO', '', ''],
    ['SERVIZI PULIZIE SRL', 'LAZIO', 'RM', 'ROMA', 'Via Prova 2', 'PULIZIE - OSA', '81.21', 'BASSO', 'Neri', 'LATINA',
     'Esposito Marco', 'M', '1990-01-15', 'SPSMRC90A15F839Y', '', 'DIPENDENTE FT', 1, 'COMMERCIO', '3',
     'Magazziniere', 40, '2022-09-01', '2025-08-31', 'TERMINATO', '', '', '', ''],
    ['', '', '', '', '', '', '', '', '', '', 'Senza Società', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
]


def workbook(rows=ROWS):
    import wr  # noqa: F401  (aggiunge vendor/ al percorso)
    import xlsxwriter
    stream = io.BytesIO()
    wb = xlsxwriter.Workbook(stream, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
    ws = wb.add_worksheet('DATABASE')
    date_fmt = wb.add_format({'num_format': 'dd/mm/yyyy'})
    ws.write_row(0, 0, HEADERS)
    for r, row in enumerate(rows, 1):
        for c, value in enumerate(row):
            if isinstance(value, str) and len(value) == 10 and value[4] == '-' and value[7] == '-':
                from datetime import date
                ws.write_datetime(r, c, date.fromisoformat(value), date_fmt)
            else:
                ws.write(r, c, value)
    wb.add_worksheet('stampa').write(0, 0, 'copia')
    wb.close()
    return stream.getvalue()


class ImportaPersonale(PortalCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / 'personale.xlsx'
        self.file.write_bytes(workbook())
        with self.portal.db.read() as con:
            uid = con.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            self.actor = users.load(con, uid)

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def test_dry_run_reads_without_writing(self):
        report = imp.run(self.portal.db, self.actor, self.file, dry_run=True, log=lambda s: None)
        self.assertEqual((report['rows'], report['skipped_rows'], report['companies']), (6, 1, 2))
        self.assertEqual(report['people'], {'total': 4, 'rows_merged': 1})
        with self.portal.db.read() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM people').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT count(*) FROM centers').fetchone()[0], 0)

    def test_import_builds_centers_people_profiles_contracts_and_links(self):
        report = imp.run(self.portal.db, self.actor, self.file, log=lambda s: None)
        self.assertEqual((report['centers_created'], report['people_created']), (2, 4))
        self.assertEqual(report['links'], 1)
        with self.portal.db.read() as con:
            codes = {r[0] for r in con.execute('SELECT code FROM centers')}
            self.assertEqual(codes, {'CENTRO-DIALISI-EST', 'SERVIZI-PULIZIE'})
            est = con.execute("SELECT id FROM centers WHERE code='CENTRO-DIALISI-EST'").fetchone()[0]
            people = {r['name']: dict(r) for r in con.execute('SELECT * FROM people WHERE center_id=?', (est,))}
            self.assertEqual(set(people), {'Bianchi Anna', 'Di Maio Luca'})
            self.assertEqual((people['Bianchi Anna']['role'], people['Di Maio Luca']['role']), ('INF', 'OSS'))
            self.assertTrue(people['Bianchi Anna']['active'])
            # stessa persona nelle due società: una sola identità di gruppo
            identities = {r[0] for r in con.execute('''SELECT p.identity_id FROM people p JOIN profiles pr ON pr.person_id=p.id
                                                       WHERE pr.fields LIKE '%BNCNNA80E44F839X%' ''')}
            self.assertEqual(len(identities), 1)
            # fascicolo: cognome/nome, codice fiscale, contratto in corso (riga più recente), campi aggiuntivi
            import json
            prof = json.loads(con.execute('SELECT fields FROM profiles WHERE person_id=?', (people['Bianchi Anna']['id'],)).fetchone()[0])
            self.assertEqual((prof['last_name'], prof['first_name'], prof['tax_code']), ('Bianchi', 'Anna', 'BNCNNA80E44F839X'))
            self.assertEqual((prof['start_date'], prof['weekly_hours'], prof['part_time_percent'], prof['relationship']),
                             ('2020-01-01', '36', '100', 'dipendente'))
            custom = json.loads(con.execute('SELECT custom FROM profiles WHERE person_id=?', (people['Bianchi Anna']['id'],)).fetchone()[0])
            self.assertEqual((custom['idoneita_scadenza'], custom['antincendio_scadenza'], custom['medico_competente']),
                             ('2027-02-09', '2028-02-09', 'Verdi'))
            custom2 = json.loads(con.execute('SELECT custom FROM profiles WHERE person_id=?', (people['Di Maio Luca']['id'],)).fetchone()[0])
            self.assertEqual(custom2['idoneita_stato'], 'DA FARE')
            prof2 = json.loads(con.execute('SELECT fields FROM profiles WHERE person_id=?', (people['Di Maio Luca']['id'],)).fetchone()[0])
            self.assertEqual((prof2['last_name'], prof2['first_name'], prof2['email']), ('Di Maio', 'Luca', ''))  # email non valida svuotata
            # due periodi di contratto per Anna nella stessa società (storico + attuale)
            n = con.execute('SELECT count(*) FROM contracts WHERE person_id=?', (people['Bianchi Anna']['id'],)).fetchone()[0]
            self.assertEqual(n, 2)
            # persona cessata: non abilitata alle presenze, fascicolo «cessato»
            pulizie = con.execute("SELECT id FROM centers WHERE code='SERVIZI-PULIZIE'").fetchone()[0]
            marco = con.execute("SELECT id, active FROM people WHERE center_id=? AND name='Esposito Marco'", (pulizie,)).fetchone()
            self.assertFalse(marco['active'])
            self.assertEqual(con.execute('SELECT stage FROM profiles WHERE person_id=?', (marco['id'],)).fetchone()[0], 'ended')
            # parametri: ruoli usati e sedi esterne diverse dal comune della società
            cfg = json.loads(con.execute('SELECT data FROM center_configs WHERE center_id=? ORDER BY version DESC LIMIT 1', (est,)).fetchone()[0])
            self.assertIn('OSS', cfg['roles'])
            self.assertEqual(cfg['sites'], ['SALERNO'])
            # rubrica della struttura
            struct = json.loads(con.execute('SELECT data FROM structures WHERE center_id=?', (est,)).fetchone()[0])
            self.assertEqual((struct['city'], struct['contact_name']), ('NAPOLI', 'Rossi'))
        self.assertTrue(any(w['field'] == 'email' for w in report['warnings']))

    def test_second_import_updates_instead_of_duplicating(self):
        imp.run(self.portal.db, self.actor, self.file, log=lambda s: None)
        report = imp.run(self.portal.db, self.actor, self.file, log=lambda s: None)
        self.assertEqual((report['centers_created'], report['centers_reused']), (0, 2))
        self.assertEqual(report['people_updated'], 3)   # le tre persone con codice fiscale
        with self.portal.db.read() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM people').fetchone()[0], 5)  # Di Maio senza codice fiscale si ripete


class Interpretazione(unittest.TestCase):
    def test_names_with_and_without_tax_code(self):
        # nomi e codici fiscali inventati
        self.assertEqual(imp.split_name('De Luca Monica', ''), ('De Luca', 'Monica'))
        self.assertEqual(imp.split_name('ROSSI GIOVANNA', 'RSSGNN70A41F839Z'), ('ROSSI', 'GIOVANNA'))
        self.assertEqual(imp.split_name('Ferrari Elena Maria', 'FRRLMR85A41F839Q'), ('Ferrari', 'Elena Maria'))
        self.assertEqual(imp.split_name('Anna Bianchi', 'BNCNNA80E44F839X'), ('Bianchi', 'Anna'))

    def test_roles_and_relationships(self):
        self.assertEqual([imp.role_of(m) for m in ('Infermiere/a', 'Direttore Sanitario', 'Add. alle pulizie', 'Medico turnista',
                                                    'OSS', 'Tecnico di laboratorio', 'Impiegato', 'Farmacista', 'Cosa strana',
                                                    'Inf.Professionale', 'O.S.S.', 'Med. Aiu. TP', 'OP. SOCIO SANIT.', 'Tecnico Rx',
                                                    'Custode', 'Coo. Inf.', 'Dir. Amm.', '')],
                         ['INF', 'DS', 'OPE', 'MED', 'OSS', 'TEC', 'AMM', 'FARM', 'ALTRO',
                          'INF', 'OSS', 'MED', 'OSS', 'TEC', 'OPE', 'INF', 'AMM', 'ALTRO'])
        self.assertEqual([imp.relationship_of(c) for c in ('DIPENDENTE FT', 'CONSULENTE', 'LEGALE RAPPRESENTANTE', '', 'Boh')],
                         ['dipendente', 'professionista', 'altro', '', 'altro'])

    def test_dates_and_codes(self):
        self.assertEqual(imp.to_date('45658'), ('2025-01-01', ''))
        self.assertEqual(imp.to_date('DA FARE'), ('', 'DA FARE'))
        self.assertEqual(imp.to_date('01/03/2024'), ('2024-03-01', ''))
        self.assertEqual(imp.to_date('2'), ('', ''))  # anno 1900: data mancante
        taken = set()
        self.assertEqual(imp.center_code('CENTRO PROVA (CENTRO ANTIDIABETICO) SCARL', taken), 'CENTRO-PROVA')
        self.assertEqual(imp.center_code('CENTRO PROVA S.R.L.', taken), 'CENTRO-PROVA-2')


if __name__ == '__main__':
    unittest.main()
