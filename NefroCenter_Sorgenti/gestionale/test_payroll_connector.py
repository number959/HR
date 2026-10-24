"""Consultant adapters are local file contracts, never presumed vendor integrations."""
import copy
import csv
import io
import json
import unittest

import core
import payroll
from test_analytics import StatisticsFixture


class PayrollConnectorTests(StatisticsFixture):
    def spec(self, **changes):
        raw = dict(schema=payroll.SPEC_SCHEMA, provider='Gestionale di prova', format_name='Presenze giornaliere',
                   format_version='2026.10', specification_reference='Specifica demo verificata',
                   delimiter=';', decimal_separator=',', date_format='DD/MM/YYYY', encoding='utf-8-sig',
                   columns=[{'header':'MATR','field':'registration','type':'text','required':True,'max_length':12},
                            {'header':'GIORNO','field':'day','type':'date','required':True,'max_length':10},
                            {'header':'CAUSALE','field':'payroll_code','type':'text','required':True,'max_length':8},
                            {'header':'ORE','field':'worked_hours','type':'decimal','required':False,'max_length':8}])
        raw.update(changes)
        return raw

    def parse(self, raw=None, **changes):
        body={'cid':self.a,'kind':'json','text':json.dumps(raw or self.spec())}
        body.update(changes)
        return payroll.spec_preview(core,self.admin,body)

    def config(self, **spec_changes):
        parsed=self.parse(self.spec(**spec_changes))
        cfg=payroll.read(core,self.admin,self.a)['config']
        cfg.update({key:parsed[key] for key in ('connector','columns','delimiter','decimal_separator')})
        cfg.update(status='confirmed',confirmation_note='Specifica verificata con il consulente')
        cfg['causes'].update(m='ORD',F='FER')
        return cfg

    def save(self,cfg=None,confirm=True):
        current=payroll.read(core,self.admin,self.a)
        return payroll.save(core,self.admin,{'cid':self.a,'expected_version':current['version'],
                            'config':cfg or self.config(),'confirm_connector':confirm})

    def preview(self):return payroll.preview(core,self.admin,self.a,'2026-10','2026-10')
    def download(self,p):return payroll.export(core,self.admin,self.a,'2026-10','2026-10','csv',p['fingerprint'])

    def test_header_only_import_is_ephemeral_and_unknown_headers_need_mapping(self):
        p=self.parse(kind='csv_header',text='Matricola consulente;Data consulente;Causale consulente;Ore',delimiter=';')
        self.assertFalse(p['stored']);self.assertEqual(p['unmapped'],4)
        self.assertEqual(p['connector']['provider'],'')
        self.assertEqual(p['connector']['mode'],'consultant')
        self.assertEqual([c['header'] for c in p['connector']['expected_columns']],['Matricola consulente','Data consulente','Causale consulente','Ore'])
        self.assertEqual(payroll.read(core,self.admin,self.a)['version'],0)
        known=self.parse(kind='csv_header',text='registration;day;payroll_code',delimiter=';')
        self.assertEqual(known['unmapped'],0)

    def test_import_rejects_employee_rows_duplicate_headers_formula_and_large_file(self):
        for text in ['A;B;C\n001;2026-10-01;ORD','A;a;C','=1;B;C','A;B;'+('x'*33000)]:
            with self.subTest(text=text[:40]),self.assertRaises(ValueError):
                self.parse(kind='csv_header',text=text)
        raw=self.spec();raw['employees']=[{'name':'Private'}]
        with self.assertRaises(ValueError):self.parse(raw)
        raw=self.spec();raw['columns'][0]['field']='unknown'
        with self.assertRaises(ValueError):self.parse(raw)
        with self.assertRaises(ValueError):self.parse(text='\ud800')

    def test_unknown_provider_and_unmapped_columns_cannot_be_confirmed(self):
        cfg=self.config(provider='non so')
        with self.assertRaisesRegex(ValueError,'gestionale'):self.save(cfg)
        cfg['status']='draft';self.save(cfg)
        self.entry();p=self.preview()
        self.assertFalse(p['can_download'])
        self.assertIn('consultant_unknown',{i['code'] for i in p['issues']})
        cfg=self.config();cfg['columns'][0]['field']=''
        with self.assertRaisesRegex(ValueError,'Associare'):self.save(cfg)

    def test_confirmation_is_explicit_for_every_version_and_stale_save_rejected(self):
        cfg=self.config()
        with self.assertRaisesRegex(ValueError,'esplicitamente'):self.save(cfg,confirm=False)
        self.save(cfg)
        with self.assertRaisesRegex(ValueError,'esplicitamente'):self.save(cfg,confirm=False)
        with self.assertRaisesRegex(ValueError,'cambiato'):
            payroll.save(core,self.admin,{'cid':self.a,'expected_version':0,'config':cfg,'confirm_connector':True})

    def test_exact_headers_order_format_decimal_and_encoding_are_exported(self):
        self.entry(end='13:30')
        cfg=self.config(encoding='cp1252');cfg['registrations']={self.person:'00017'}
        self.save(cfg);p=self.preview()
        self.assertEqual(p['connector_status'],'verified');self.assertTrue(p['can_download'])
        rows=list(csv.reader(io.StringIO(self.download(p).decode('cp1252')),delimiter=';'))
        self.assertEqual(rows,[['MATR','GIORNO','CAUSALE','ORE'],['00017','04/10/2026','ORD','6,5']])
        self.assertEqual(p['output_format']['date_format'],'DD/MM/YYYY')
        self.assertEqual(p['summary']['known_minutes'],390)

    def test_headers_order_and_source_types_must_match_contract(self):
        cfg=self.config();cfg['columns'][0],cfg['columns'][1]=cfg['columns'][1],cfg['columns'][0]
        with self.assertRaisesRegex(ValueError,'ordine'):self.save(cfg)
        cfg=self.config();cfg['connector']['expected_columns'][0]['type']='integer'
        with self.assertRaisesRegex(ValueError,'tipo'):self.save(cfg)
        cfg=self.config();cfg['connector']['expected_columns'][0]['header']='=MATR'
        with self.assertRaises(ValueError):self.save(cfg)

    def test_length_missing_optional_and_encoding_are_checked_before_download(self):
        self.entry(kind='absence',code='F',start='',end='')
        cfg=self.config();self.save(cfg)
        p=self.preview();self.assertTrue(p['can_download'])
        self.assertIsNone(p['rows'][0][-1])
        cfg['connector']['expected_columns'][-1]['required']=True;self.save(cfg)
        p=self.preview();self.assertFalse(p['can_download'])
        self.assertIn('dato obbligatorio mancante',' '.join(i['message'] for i in p['issues']))
        cfg['connector']['expected_columns'][-1]['required']=False
        cfg['connector']['expected_columns'][0]['max_length']=2;self.save(cfg)
        self.assertIn('lunghezza massima',' '.join(i['message'] for i in self.preview()['issues']))
        cfg['connector']['expected_columns'][0]['max_length']=12
        cfg['connector']['encoding']='cp1252';cfg['registrations'][self.person]='測試';self.save(cfg)
        p=self.preview();self.assertFalse(p['can_download'])
        self.assertIn('codifica',' '.join(i['message'] for i in p['issues']))
        with self.assertRaises(ValueError):self.download(p)

    def test_formula_data_is_blocked_in_exact_consultant_file(self):
        self.entry();cfg=self.config();cfg['registrations'][self.person]='=1+1';self.save(cfg)
        p=self.preview();self.assertFalse(p['can_download'])
        self.assertIn('prefisso di formula',' '.join(i['message'] for i in p['issues']))
        with self.assertRaises(ValueError):self.download(p)

    def test_specification_roundtrip_excludes_employee_data_and_mapping(self):
        cfg=self.config();cfg['registrations'][self.person]='PRIVATE-MAT';cfg['causes']['m']='PRIVATE-CAUSE';self.save(cfg)
        portable=payroll.specification(core,self.admin,self.a)
        text=json.dumps(portable)
        self.assertNotIn('PRIVATE',text);self.assertNotIn(self.person,text)
        self.assertEqual(set(portable),set(self.spec()))
        parsed=self.parse(portable)
        self.assertEqual(parsed['connector'],cfg['connector'])
        self.assertEqual(parsed['columns'],cfg['columns'])
        parsed_bom=self.parse(text='\ufeff'+text)
        self.assertEqual(parsed_bom['connector'],cfg['connector'])

    def test_import_and_specification_require_current_hr_permissions(self):
        for user in (self.operator,self.viewer):
            with self.assertRaises(PermissionError):payroll.spec_preview(core,user,{'cid':self.a,'kind':'json','text':json.dumps(self.spec())})
            with self.assertRaises(PermissionError):payroll.specification(core,user,self.a)
        with core.connect() as c:
            c.execute("UPDATE users SET role='viewer' WHERE id=?",(self.admin['id'],));c.commit()
        with self.assertRaises(PermissionError):payroll.specification(core,self.admin,self.a)


if __name__=='__main__':unittest.main()
