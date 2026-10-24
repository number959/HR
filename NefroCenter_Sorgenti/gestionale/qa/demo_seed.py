"""Generate only synthetic, public demo fixtures. Never opens a configured database."""
import sys,tempfile,json,base64,secrets
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import core,hr,agreements,analytics,excel_exports,workforce,payroll,tasks,backup_policy,backup_tools,structures,communications
from rules import defaults


def pdf():
    stream=b'BT /F1 22 Tf 60 760 Td (DOCUMENTO DIMOSTRATIVO) Tj 0 -42 Td /F1 12 Tf (NefroCenter - Demo con dati fittizi) Tj 0 -30 Td (Questo documento non ha valore contrattuale.) Tj 0 -22 Td (Non contiene dati di dipendenti reali.) Tj ET'
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    out=b'%PDF-1.4\n';offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(len(out));out+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(out);out+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets[1:])+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode();return out


def build(destination):
    destination.mkdir(parents=True,exist_ok=True);samples=destination/'samples';samples.mkdir(exist_ok=True)
    sample_pdf=pdf();(samples/'contratto-demo.pdf').write_bytes(sample_pdf)
    with tempfile.TemporaryDirectory(prefix='nefrocenter-public-demo-') as td:
        core.DB=Path(td)/'data'/'presenze.sqlite3';core.init_db();structures.init(core);communications.init(core)
        core.setup(dict(username='demo.admin',password=secrets.token_urlsafe(40),name='Amministrazione · demo',center_name='Capodichino · Demo'))
        with core.connect() as c:
            admin=core.public_user(c.execute('SELECT * FROM users').fetchone());first=core.centers_for(c,admin)[0]['id']
        center_ids=[first]+[core.mutate(admin,'center_create',dict(name=name,code=code))['cid'] for name,code in [('Vomero · Demo','DEMO-VOM'),('Pozzuoli · Demo','DEMO-POZ')]]
        names=[['Anna Rossi','Marco Bianchi','Elena Costa','Paolo Greco'],['Lucia Verdi','Andrea Riva','Sara Conti','Matteo Villa'],['Anna Rossi','Giulia Serra','Luca Moretti','Chiara Ferri']]
        roles=['INF','MED','OSS','INF'];by_center={};number=0
        for ci,cid in enumerate(center_ids):
            structures.save(core,admin,dict(cid=cid,version=0,fields=dict(legal_name=['Capodichino','Vomero','Pozzuoli'][ci]+' Demo S.r.l. — dati fittizi',address=f'Via Dimostrativa {ci+1}',city='Napoli' if ci<2 else 'Pozzuoli',postal_code='00000',province='NA',phone=f'000-DEMO-00{ci+1}',email=f'sede{ci+1}@example.invalid',hr_email=f'hr.sede{ci+1}@example.invalid',admin_email=f'amministrazione.sede{ci+1}@example.invalid',pec=f'pec.sede{ci+1}@example.invalid',contact_name='Referente dimostrativo',director='Direttore dimostrativo',website='https://example.invalid',notes='Rubrica fittizia per provare le comunicazioni. Nessun recapito reale.')))
            by_center[cid]=[]
            for pi,name in enumerate(names[ci]):
                number+=1
                with core.connect() as c:revision=core.center(c,cid)['revision']
                fields=dict(first_name=name.split()[0],last_name=name.split()[1],email=f'persona{number}@example.invalid',company_email=f'demo{number}@example.invalid',department='Dialisi',start_date='2026-09-01',identity_type='Facsimile',identity_number=f'DEMO-{number:03}',identity_expiry='2026-11-10' if pi==0 else '2027-12-31',contract_type='Tempo indeterminato',weekly_hours='36',part_time_percent='100')
                pid=hr.save(core,admin,dict(cid=cid,revision=revision,version=0,name=name,role=roles[pi],registration=f'DEMO{number:03}',active=True,stage='incoming' if pi==3 else 'active',fields=fields,custom={}))['pid'];by_center[cid].append(pid)
                record=hr.read(core,admin,cid,pid)
                for task in record['profile']['tasks'][:(3 if pi==3 else 12)]:
                    record=hr.read(core,admin,cid,pid)
                    hr.task_save(core,admin,dict(cid=cid,pid=pid,version=record['profile']['version'],task_id=task['id'],status='done',note='Verifica dimostrativa',due='',owner='HR demo'))
                if pi<2:hr.document_add(core,admin,dict(cid=cid,pid=pid,name='contratto-demo.pdf',category='Contratto',expiry='2026-11-10' if pi==0 else '',content=base64.b64encode(sample_pdf).decode()))
                with core.connect() as c:assignment=workforce.ensure_person(c,cid,pid)
                workforce.mutate(core,admin,'workforce_contract',dict(cid=cid,pid=pid,assignment_version=assignment['version'],effective_from='2026-09-01',effective_to='',version=0,reason='Condizioni esclusivamente dimostrative',data=dict(role=roles[pi],contract_type='Tempo indeterminato',ccnl='Esempio da verificare',level='Livello demo',weekly_hours=36,part_time_percent=100,note='Dati fittizi')))
                with core.connect() as c:
                    cfg=core.center(c,cid)['config'];assignment=workforce.ensure_person(c,cid,pid)
                a={**agreements.proposal(cfg,{}),'basis':'all','fixed_deduction':0,'confirmed':True}
                workforce.mutate(core,admin,'workforce_economic',dict(cid=cid,pid=pid,assignment_version=assignment['version'],effective_from='2026-10-01',effective_to='',version=0,reason='Tariffe soltanto dimostrative',data=a))
                with core.connect() as c:
                    center=core.center(c,cid);cfg=center['config']
                    for d in range(1,24):
                        if date(2026,10,d).weekday()==6:continue
                        if ci==2 and pi==0 and d%2==0:continue
                        if ci==0 and pi==0 and d%2!=0:continue
                        if pi==3 and d<12:continue
                        slot=cfg['slots'][(pi+ci)%2];code='FE' if d in (8,9) and pi==2 else slot['id'];causal=next(x for x in cfg['codes'] if x['id']==code);layer='planned' if d>18 else 'actual'
                        missing=ci==0 and pi==1 and d==16
                        e=dict(id=core.uid(),person_id=pid,day=f'2026-10-{d:02}',slot=slot['id'],code=code,code_label=causal['label'],layer=layer,kind=causal['kind'],start='' if causal['kind']!='work' or missing else slot['start'],end='' if causal['kind']!='work' or missing else slot['end'],pause=0,overnight=False,holiday=False,work_site=center['name'],credit_minutes=0,note='Registrazione dimostrativa',config_version=1,updated_by='demo.admin',updated_at='2026-10-18T10:00:00+00:00')
                        core.put(c,'entries',cid,e)
                    period=core.period(c,center,'2026-10');period['verified']=ci!=0;core.put_period(c,cid,'2026-10',period);c.commit()
                current=workforce.preview(core,admin,cid,pid,'2026-10')
                with core.connect() as c:assignment=workforce.ensure_person(c,cid,pid)
                workforce.mutate(core,admin,'workforce_apply',dict(cid=cid,pid=pid,assignment_version=assignment['version'],month='2026-10',revision=current['revision'],reason='Accordo dimostrativo del mese'))
            with core.connect() as c:
                for d in [1,2,3,5,6,7,8,9,10,12,13,14,15,16,17]:
                    core.put(c,'patients',cid,dict(id=f'2026-10-{d:02}|m',day=f'2026-10-{d:02}',slot='m',ordinary=12+ci*2,isolated=1))
                c.commit()
        with core.connect() as c:
            source=workforce.ensure_person(c,center_ids[2],by_center[center_ids[2]][0]);target=workforce.ensure_person(c,first,by_center[first][0]);version=c.execute('SELECT version FROM group_people WHERE id=?',(target['global_id'],)).fetchone()[0]
        workforce.mutate(core,admin,'workforce_link',dict(cid=center_ids[2],pid=source['pid'],assignment_version=source['version'],global_id=target['global_id'],target_version=version,reason='La stessa persona fittizia opera in due centri'))
        for role,name in [('hr','Ufficio HR · demo'),('manager','Responsabile · demo'),('operator','Compilatore · demo'),('viewer','Direzione · demo')]:
            core.mutate(admin,'user_save',dict(user=dict(username='demo.'+role,name=name,role=role,centers=[] if role=='hr' else center_ids[:1] if role in ('manager','operator') else center_ids,active=True,password=secrets.token_urlsafe(40))))
        with core.connect() as c:centers=core.centers_for(c,admin);users=[core.public_user(r) for r in c.execute('SELECT * FROM users')]
        communications.save_list(core,admin,dict(version=0,name='Dipendenti attivi · tutte le sedi demo',cids=[],roles=[],stages=['active'],email_field='company_email',recipient_type='employees',structure_field='email',exclude_emails=[]))
        communications.save_list(core,admin,dict(version=0,name='Referenti HR · strutture demo',cids=[],roles=[],stages=[],email_field='company_email',recipient_type='structures',structure_field='hr_email',exclude_emails=[]))
        out=dict(version='0.11',month='2026-10',centers=centers,users=users,snapshots={},hrLists={},hrDetails={},structures=structures.read(core,admin),workforce=workforce.read(core,admin,on='2026-10-19'),workforceDetails={},workforcePreviews={},tasks=tasks.report(core,admin,'2026-10'),payrollConfigs={},payrollPreviews={},statistics={},agreements={},documents=hr.document_index(core,admin),backupPolicy=backup_policy.status(core,admin),backups=backup_tools.listing(core,admin),security=dict(enabled=True,recovery_remaining=10,sessions=1,history=[],recent=True))
        out['backups']['files']=[];out['backups']['count']=0;out['backups']['bytes']=0;out['backups']['shown']=0
        out['communications']=communications.overview(core,admin)
        for ct in centers:
            cid=ct['id'];out['snapshots'][cid]=core.snapshot(admin,cid,'2026-10');out['hrLists'][cid]=hr.read(core,admin,cid);out['hrDetails'][cid]={pid:hr.read(core,admin,cid,pid) for pid in by_center[cid]};out['workforcePreviews'][cid]={pid:workforce.preview(core,admin,cid,pid,'2026-10') for pid in by_center[cid]};out['payrollConfigs'][cid]=payroll.read(core,admin,cid);out['payrollPreviews'][cid]=payroll.preview(core,admin,cid,'2026-10','2026-10');out['statistics'][cid]=analytics.report(core,admin,'2026-10','2026-10',cid);out['agreements'][cid]=agreements.report(core,admin,cid,'2026-10')
            for kind in excel_exports.KINDS:
                (samples/f'{kind}_{cid}.xlsx').write_bytes(excel_exports.export(core,admin,kind,'2026-10','2026-10',cid))
        out['statistics']['all']=analytics.report(core,admin,'2026-10','2026-10')
        for kind in excel_exports.KINDS:
            if kind!='presenze_centro':(samples/f'{kind}_all.xlsx').write_bytes(excel_exports.export(core,admin,kind,'2026-10','2026-10'))
        for g in out['workforce']['groups']:out['workforceDetails'][g['global_id']]=workforce.read(core,admin,g['global_id'],on='2026-10-19')
        (destination/'demo_seed.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')))
        print(json.dumps(dict(centers=len(centers),people=sum(len(p) for p in by_center.values()),identities=len(out['workforce']['groups']),documents=out['documents']['total'],bytes=(destination/'demo_seed.json').stat().st_size)))

if __name__=='__main__':build(Path(sys.argv[1]))
