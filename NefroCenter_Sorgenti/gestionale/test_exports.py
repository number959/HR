"""Read XLSX packages independently with stdlib OOXML; no Excel test dependency."""
import io
import json
import sqlite3
import unittest
import zipfile
from unittest.mock import patch
from xml.etree import ElementTree as ET
import analytics
import backup_tools
import core
import excel_exports
import hr
import test_analytics

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read_xlsx(raw):
    out={}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        shared=ET.fromstring(z.read('xl/sharedStrings.xml'))
        strings=[''.join(n.itertext()) for n in shared]
        book=ET.fromstring(z.read('xl/workbook.xml'))
        for i,node in enumerate(book.findall('s:sheets/s:sheet',NS),1):
            xml=ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml'));cells={}
            for cell in xml.findall('.//s:sheetData/s:row/s:c',NS):
                value=cell.find('s:v',NS);v=value.text if value is not None else None
                if cell.get('t')=='s':v=strings[int(v)]
                elif v is not None:v=float(v)
                cells[cell.get('r')]=v
            out[node.get('name')]=cells
            if xml.find('.//s:f',NS) is not None:raise AssertionError('Unexpected Excel formula')
            if xml.find('.//s:hyperlink',NS) is not None:raise AssertionError('Unexpected automatic hyperlink')
    return out


class ExportTests(test_analytics.StatisticsFixture):
    def export(self,kind='presenze_centro',user=None,**filters):
        return excel_exports.export(core,user or self.admin,kind,'2026-10','2026-10',**{'cid':self.a,**filters})

    def test_native_workbook_grid_typed_hours_and_missing_values(self):
        self.entry(start='22:00',end='04:00',overnight=True,pause=60)
        self.entry(day='2026-10-05',start='',end='')
        book=read_xlsx(self.export())
        self.assertEqual(set(book),{'Registro mensile','Totali persona','Dettaglio','Legenda','Informazioni'})
        self.assertAlmostEqual(book['Totali persona']['F5']*1440,300)
        self.assertEqual((book['Totali persona']['D5'],book['Totali persona']['G5']),(2,1))
        self.assertEqual(book['Registro mensile']['H5'],'m') # day 4
        self.assertIsInstance(book['Dettaglio']['E5'],float)
        self.assertIsNone(book['Dettaglio']['O6'])

    def test_aggregate_export_reconciles_and_empty_month_stays_blank(self):
        self.entry();self.entry(self.b,work_site='Centro B',start='',end='')
        raw=excel_exports.export(core,self.admin,'presenze_totali','2026-10','2026-11')
        b=read_xlsx(raw)
        self.assertAlmostEqual(b['Totali']['B5']*1440,360)
        self.assertEqual((b['Totali']['C5'],b['Totali']['F5'],b['Totali']['G5']),(2,1,.5))
        self.assertIsNone(b['Andamento']['B6'])
        self.assertEqual(len(b['Centri']),len(read_xlsx(self.export('statistiche',cid='all'))['Centri']))

    def test_formula_strings_preserved_as_text_and_no_auto_hyperlinks(self):
        with core.connect() as c:
            p=core.objects(c,'people',self.a)[0];core.put(c,'people',self.a,{**p,'name':'=1+1'});c.commit()
        self.entry(note='https://example.invalid')
        b=read_xlsx(self.export());self.assertEqual(b['Totali persona']['A5'],'=1+1')
        self.assertEqual(b['Dettaglio']['Q5'],'https://example.invalid')

    def test_hr_onboarding_and_unconfirmed_agreements_export(self):
        with core.connect() as c:
            p=hr.profile(c,self.a,self.person);p['fields']={'iban':'IT-DEMO-PRIVATE','identity_expiry':'2027-01-02'}
            c.execute('INSERT INTO hr_profiles VALUES (?,?,?,?)',(self.a,self.person,1,json.dumps(p)));c.commit()
        self.assertEqual(len(hr.FIELDS),len(excel_exports.HR_LABELS))
        b=read_xlsx(self.export('dipendenti'));self.assertIn('IT-DEMO-PRIVATE',b['Fascicoli'].values())
        self.assertIn('Attività',read_xlsx(self.export('onboarding')))
        a=read_xlsx(self.export('accordi'));self.assertIsNone(a['Accordi']['O5']);self.assertEqual(a['Accordi']['G5'],'NO')
        for kind in ['presenze_centro','presenze_totali','statistiche']:
            public=json.dumps(read_xlsx(self.export(kind,user=self.viewer)))
            self.assertNotIn('IT-DEMO-PRIVATE',public)

    def test_permissions_for_every_export_and_revoked_export_flag(self):
        for kind in excel_exports.PRIVATE:
            with self.subTest(kind=kind),self.assertRaises(PermissionError):self.export(kind,user=self.operator)
        for kind in ['presenze_centro','presenze_totali','statistiche']:
            with self.subTest(kind=kind),self.assertRaises(PermissionError):self.export(kind,user=self.operator,cid=self.b)
        cfg=core.snapshot(self.admin,self.a,'2026-10')['center']['config'];cfg['operator_export']=False
        core.mutate(self.admin,'center_save',{**self.req(),'config':cfg})
        with self.assertRaises(PermissionError):self.export(user=self.viewer)
        with self.assertRaises(PermissionError):self.export('presenze_totali',user=self.operator,cid='all')

    def test_hr_numeric_fields_are_numbers_and_identifiers_remain_text(self):
        with core.connect() as c:
            p=core.objects(c,'people',self.a)[0]
            core.put(c,'people',self.a,{**p,'registration':'000123'})
            profile=hr.profile(c,self.a,self.person)
            profile['fields'].update(weekly_hours='36,5',part_time_percent='80,25',postal_code='00100')
            c.execute('INSERT INTO hr_profiles VALUES (?,?,?,?)',(self.a,self.person,1,json.dumps(profile)))
            c.commit()
        raw=self.export('dipendenti');cells=read_xlsx(raw)['Fascicoli']
        def data_cell(label):
            header=next(cell for cell,value in cells.items() if value==label)
            return header[:-1]+'5'
        self.assertEqual(cells[data_cell('Ore settimanali')],36.5)
        self.assertAlmostEqual(cells[data_cell('Part-time %')],.8025)
        self.assertEqual(cells[data_cell('Matricola')],'000123')
        self.assertEqual(cells[data_cell('CAP')],'00100')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            percent_cell=xml.find(".//s:c[@r='"+data_cell('Part-time %')+"']",NS)
            styles=ET.fromstring(z.read('xl/styles.xml'))
            number_format=styles.find('s:cellXfs',NS)[int(percent_cell.get('s'))].get('numFmtId')
            self.assertEqual(styles.find("s:numFmts/s:numFmt[@numFmtId='"+number_format+"']",NS).get('formatCode'),'0.00%')
        empty=read_xlsx(self.export('dipendenti',cid=self.b))['Fascicoli']
        self.assertIsNone(empty[data_cell('Ore settimanali')])
        self.assertIsNone(empty[data_cell('Part-time %')])

    def test_plan_and_actual_are_separate_and_invalid_requests_rejected(self):
        self.entry();self.entry(day='2026-10-05',layer='planned',start='08:00',end='10:00')
        self.assertAlmostEqual(read_xlsx(self.export(layer='planned'))['Totali persona']['F5']*1440,120)
        self.assertAlmostEqual(read_xlsx(self.export())['Totali persona']['F5']*1440,360)
        with self.assertRaises(ValueError):self.export(cid='all')
        with self.assertRaises(ValueError):self.export(kind='missing')
        self.entry(person_id='deleted')
        with self.assertRaises(ValueError):self.export()
        with self.assertRaises(ValueError):self.export('statistiche')

    def test_backup_integrity_attachments_scope_and_completed_files_only(self):
        content=b'Documento allegato demo'
        with core.connect() as c:
            c.execute('INSERT INTO hr_documents VALUES (?,?,?,?,?,?,?,?,?,?)',('doc',self.a,self.person,'demo.txt','Altro','','2026-10-17','admin','demo',content));c.commit()
        name=core.backup(self.admin)['filename'];directory=core.DB.parent/'backups'
        (directory/(name+'.partial')).write_bytes(b'incomplete')
        (directory/'presenze_20000101_000000_000000.sqlite3').symlink_to(core.DB)
        listing=backup_tools.listing(core,self.admin)
        self.assertTrue(all(not x['filename'].endswith('.partial') for x in listing['files']))
        self.assertNotIn('presenze_20000101_000000_000000.sqlite3',[x['filename'] for x in listing['files']])
        raw=backup_tools.download(core,self.admin,name);self.assertTrue(raw.startswith(b'SQLite format 3'))
        with sqlite3.connect(directory/name) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT content FROM hr_documents').fetchone()[0],content)
        for call in [lambda:backup_tools.listing(core,self.operator),lambda:backup_tools.download(core,self.viewer,name)]:
            with self.assertRaises(PermissionError):call()
        for invalid in ['../presenze.sqlite3','presenze_20000101_000000_000000.sqlite3',name+'.partial']:
            with self.assertRaises(ValueError):backup_tools.download(core,self.admin,invalid)
        with patch.object(backup_tools,'MAX_DOWNLOAD',1):
            self.assertFalse(backup_tools.listing(core,self.admin)['files'][0]['downloadable'])
            with self.assertRaises(ValueError):backup_tools.download(core,self.admin,name)


if __name__=='__main__':unittest.main(verbosity=2)
