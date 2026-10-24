"""Casi anonimi: accordi mensili, contatori Excel e confini di autorizzazione."""
import copy,unittest
import agreements,rules,import_excel

class AgreementCalculationTests(unittest.TestCase):
    def setUp(self):
        self.cfg=rules.defaults();self.person=dict(id='p1',name='Persona demo',role='INF')
        self.a={**agreements.proposal(self.cfg,self.person),'confirmed':True}
    def entry(self,day=2,code='m',**extra):
        c=next(c for c in self.cfg['codes'] if c['id']==code)
        return dict(person_id='p1',day='2026-02-'+str(day).zfill(2),slot='m',layer='actual',code=code,kind=c['kind'],start='07:00',end='13:00',pause=0,overnight=False,holiday=False,work_site='Centro A',credit_minutes=c['credit_minutes'],**extra)
    def calc(self,es,**ag):return agreements.calculate(self.person,es,'2026-02','Centro A',self.cfg,{**self.a,**ag})
    def test_real_february_calendar_and_negative_preserved(self):
        r=self.calc([self.entry()]);self.assertEqual(r['calendar_days'],24);self.assertEqual(r['ordinary_units'],-23);self.assertEqual(r['amount'],-1250);self.assertEqual(r['status'],'da_verificare')
    def test_manual_theoretical_and_deduction_zero(self):
        r=self.calc([self.entry()],theoretical_mode='manual',theoretical_units=1,fixed_deduction=0);self.assertEqual(r['amount'],0)
        self.assertIsNone(self.calc([self.entry()],confirmed=False)['amount'])
    def test_festive_all_turns_and_individual_rates(self):
        es=[self.entry(),{**self.entry(3),'holiday':True}];r=self.calc(es,basis='all',weekday_rate=45,holiday_rate=80,fixed_deduction=0);self.assertEqual(r['amount'],125);self.assertEqual(r['ordinary_units'],1)
    def test_absence_selection_and_external_policy(self):
        es=[self.entry(),self.entry(3,'FE'),self.entry(4,'RC'),{**self.entry(5),'work_site':'Centro B'}]
        self.assertEqual(self.calc(es,basis='all')['units'],3)
        r=self.calc(es,basis='all',counted_absences=['RC'],include_external=False,fixed_deduction=0);self.assertEqual(r['units'],2);self.assertEqual(r['external'],1);self.assertEqual(r['amount'],100)
    def test_hours_missing_are_not_invented(self):
        es=[{**self.entry(),'start':'','end':''}];r=self.calc(es,model='hours',basis='all');self.assertIsNone(r['amount']);self.assertEqual(r['status'],'orari_mancanti')
    def test_hours_credits_and_rounding(self):
        es=[{**self.entry(),'end':'07:01'},{**self.entry(3,'FE'),'credit_minutes':60}]
        r=self.calc(es,model='hours',basis='all',weekday_rate=10,fixed_deduction=0);self.assertEqual(r['amount'],10.17)
    def test_fixed_model_and_ccnl_explicit_only(self):
        self.assertEqual(self.a['ccnl_rate'],0)
        r=self.calc([],model='fixed',fixed_amount=1500,fixed_deduction=100,ccnl_count=2,ccnl_rate=20,adjustment=-5);self.assertEqual(r['amount'],1355)
    def test_other_people_months_and_planned_excluded(self):
        es=[self.entry(),{**self.entry(),'person_id':'p2'},{**self.entry(),'day':'2026-03-02'},{**self.entry(),'layer':'planned'}];self.assertEqual(self.calc(es,basis='all')['units'],1)
    def test_no_presence_is_empty_not_negative_payment(self):
        r=self.calc([]);self.assertIsNone(r['amount']);self.assertEqual(r['status'],'nessun_dato')
    def test_invalid_parameters_rejected(self):
        for patch in ({'weekday_rate':float('nan')},{'confirmed':'yes'},{'counted_absences':['unknown']},{'ccnl_count':1.5},{'model':'eval(...)'},{'hours_per_day':0},{'theoretical_units':.5}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):agreements.validate({**self.a,**patch},self.cfg)
    def test_saved_proposal_survives_default_changes(self):
        p={'config':copy.deepcopy(self.cfg)};agreements.freeze(p,[self.person]);p['config']['weekday_rate']=200;agreements.freeze(p,[self.person]);self.assertEqual(p['agreements']['p1']['weekday_rate'],50)
    def formulas(self,all_turns=False,deduction=100,exclude_rc=True):
        return {k:{'formula_text':v} for k,v in {'AT10':'93-COUNTBLANK(D10:AH12)'+('-AN10' if exclude_rc else ''),'AV12':'AT10' if all_turns else 'IF(AT10<=0,"",AT10-$X$3)','AW12':'IF(AV12="","",AV12-AY12)','AX12':'IF(AW12="","",AW12*50)','AZ12':'IF(AY12="","",AY12*70)','BA12':'IF(AX12="","",AX12+AZ12'+('-'+str(deduction) if deduction else '')+')'}.items()}
    def test_recognizes_formula_variants_without_evaluation(self):
        for all_turns,deduction,exclude_rc in [(False,100,False),(False,0,True),(True,0,True)]:
            a=import_excel.recognized_agreement(self.formulas(all_turns,deduction,exclude_rc),10);self.assertEqual(a['basis'],'all' if all_turns else 'surplus');self.assertEqual(a['fixed_deduction'],deduction);self.assertEqual('RC' in a['counted_absences'],not exclude_rc);self.assertFalse(a['confirmed']);self.assertEqual(a['ccnl_rate'],0)
        f=self.formulas();f['BA12']['formula_text']='WEBSERVICE("https://example.invalid/")';self.assertIsNone(import_excel.recognized_agreement(f,10))
        a=import_excel.recognized_agreement(self.formulas(True,0),10)
        self.assertEqual(self.calc([self.entry(2,'R')],**{**a,'confirmed':True})['units'],1)

if __name__=='__main__':unittest.main()
