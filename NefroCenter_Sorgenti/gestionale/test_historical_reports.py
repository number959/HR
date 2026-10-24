"""Date-effective role filters agree across summaries and native Excel exports."""
import unittest

import analytics
import core
import excel_exports
import workforce
from test_analytics import StatisticsFixture
from test_exports import read_xlsx


class HistoricalReportsTests(StatisticsFixture):
    def setUp(self):
        super().setUp()
        with core.connect() as c:
            person=core.objects(c,'people',self.a)[0]
            core.put(c,'people',self.a,{**person,'role':'OSS'})
            c.commit()

    def contract(self,start,end,role,record=None):
        with core.connect() as c:
            assignment=workforce._assignment(c,self.a,self.person)
        body=dict(cid=self.a,pid=self.person,assignment_version=assignment['version'],
                  reason='Ricostruzione verificata del contratto',effective_from=start,effective_to=end,
                  data=dict(role=role,contract_type='Indeterminato',weekly_hours=36,part_time_percent=100))
        if record:
            body.update(id=record['id'],version=record['version'])
        return workforce.mutate(core,self.admin,'workforce_contract',body)['record']

    def report(self,**filters):
        return analytics.report(core,self.admin,'2026-10','2026-10',**{'cid':self.a,**filters})

    def export(self,kind='presenze_centro',**filters):
        return read_xlsx(excel_exports.export(core,self.admin,kind,'2026-10','2026-10',**{'cid':self.a,**filters}))

    def test_intramonth_roles_filter_every_metric_and_keep_person_count_distinct(self):
        self.contract('2026-10-01','2026-10-15','INF')
        self.contract('2026-10-16','2026-10-31','MED')
        self.entry(day='2026-10-15',start='07:00',end='09:00')
        self.entry(day='2026-10-16',start='08:00',end='11:00')
        self.entry(day='2026-10-15',layer='planned')
        data=self.report()
        self.assertEqual((data['summary']['minutes'],data['summary']['people_count']),(300,1))
        self.assertEqual({r['role']:r['minutes'] for r in data['by_role']},{'INF':120,'MED':180})
        self.assertEqual(data['by_person'][0]['roles'],['INF','MED'])
        self.assertEqual(data['quality']['current_role_fallback_records'],0)
        for role,minutes in [('INF',120),('MED',180)]:
            selected=self.report(role=role)
            self.assertEqual(selected['summary']['minutes'],minutes)
            self.assertEqual(selected['monthly'][0]['minutes'],minutes)
            self.assertEqual(selected['by_center'][0]['minutes'],minutes)
            self.assertEqual(selected['by_person'][0]['role'],role)
            self.assertEqual(selected['by_role'][0]['role'],role)
            self.assertEqual([p['id'] for p in selected['options']['people']],[self.person])
        self.assertEqual(self.report(role='INF')['summary']['pending_work'],0)
        # The current role is not retroactively applied to covered dates.
        self.assertIsNone(self.report(role='OSS')['summary']['minutes'])

    def test_missing_contract_dates_use_explicit_current_role_fallback(self):
        self.contract('2026-09-01','2026-10-15','INF')
        self.contract('2026-10-17','','MED')
        for day in ('15','16','17'):
            self.entry(day='2026-10-'+day)
        data=self.report()
        self.assertEqual(data['quality']['current_role_fallback_records'],1)
        self.assertEqual({r['role'] for r in data['by_role']},{'INF','OSS','MED'})
        self.assertEqual(self.report(role='OSS')['summary']['work_shifts'],1)
        self.assertIn('senza ricostruire lo storico',data['role_history_note'])
        with core.connect() as c:
            choices=analytics.period_roles(c,self.a,core.objects(c,'people',self.a),'2026-10','2026-10')
        self.assertEqual(choices[self.person],{'INF','OSS','MED'})

    def test_adjacent_contracts_cover_period_without_current_role_and_other_centers_are_independent(self):
        self.contract('2026-09-01','2026-10-15','INF')
        self.contract('2026-10-16','','AMM')
        with core.connect() as c:
            choices=analytics.period_roles(c,self.a,core.objects(c,'people',self.a),'2026-10','2026-11')
        self.assertEqual(choices[self.person],{'INF','AMM'})
        self.entry(day='2026-10-16')
        self.entry(self.b,day='2026-10-16',work_site='Centro B')
        data=self.report(cid='all')
        self.assertEqual({r['role'] for r in data['by_role']},{'AMM','MED'})
        self.assertEqual(data['summary']['people_count'],2)
        self.assertEqual(self.report(cid='all',role='AMM')['summary']['people_count'],1)

    def test_native_monthly_and_statistics_exports_reconcile_historical_role_filters(self):
        self.contract('2026-10-01','2026-10-15','INF')
        self.contract('2026-10-16','2026-10-31','MED')
        self.entry(day='2026-10-15',start='07:00',end='09:00')
        self.entry(day='2026-10-16',start='',end='')
        self.entry(day='2026-10-20',layer='planned',start='08:00',end='12:00')
        full=self.export()
        self.assertEqual(full['Totali persona']['C5'],'INF / MED')
        self.assertEqual((full['Dettaglio']['D5'],full['Dettaglio']['D6']),('INF','MED'))
        self.assertIsNone(full['Dettaglio']['O6'])
        self.assertEqual(full['Totali persona']['G5'],1)
        for role in ('INF','MED'):
            report=self.report(role=role)
            book=self.export(role=role)
            stats=self.export(kind='statistiche',role=role)
            self.assertEqual(book['Totali persona']['C5'],role)
            self.assertEqual(book['Totali persona']['D5'],report['summary']['work_shifts'])
            self.assertEqual(stats['Ruoli']['A5'],role)
            self.assertEqual(stats['Ruoli']['A4'],'Ruolo alla data')
            self.assertEqual(stats['Totali']['C5'],report['summary']['work_shifts'])
            minutes=book['Totali persona']['F5']
            if report['summary']['minutes'] is None:
                self.assertIsNone(minutes)
            else:
                self.assertAlmostEqual(minutes*1440,report['summary']['minutes'])
            self.assertEqual(book['Dettaglio']['D5'],role)
        planned=self.export(role='MED',layer='planned')
        self.assertEqual(planned['Dettaglio']['D5'],'MED')
        self.assertAlmostEqual(planned['Totali persona']['F5']*1440,240)

    def test_hr_exports_and_summary_keep_current_role_semantics(self):
        self.contract('2026-10-01','2026-10-31','INF')
        self.entry()
        self.assertEqual(self.report(role='INF')['summary']['work_shifts'],1)
        self.assertEqual(self.report(role='INF')['hr']['active_people'],0)
        self.assertEqual(self.report(role='OSS')['hr']['active_people'],1)
        current=self.export(kind='dipendenti',role='OSS')
        self.assertEqual(current['Fascicoli']['D5'],'OSS')
        historical=self.export(kind='dipendenti',role='INF')
        self.assertEqual(historical['Fascicoli']['A5'],'Nessun dato nei filtri selezionati.')
        self.assertIn('Ruolo, anagrafica e fascicolo sono quelli attuali',
                      ' '.join(str(v) for v in current['Informazioni'].values()))

    def test_explicit_history_correction_updates_closed_month_report_with_disclosure(self):
        record=self.contract('2026-10-01','2026-10-31','INF')
        self.entry()
        core.mutate(self.admin,'period_verify',{**self.req(),'verified':True})
        core.mutate(self.admin,'close',self.req())
        self.contract('2026-10-01','2026-10-31','MED',record=record)
        data=self.report()
        self.assertTrue(data['center_months'][0]['closed'])
        self.assertEqual(data['by_role'][0]['role'],'MED')
        self.assertIn('anche nei report di mesi chiusi',data['role_history_note'])
        with core.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM workforce_history').fetchone()[0],2)


if __name__=='__main__':
    unittest.main(verbosity=2)
