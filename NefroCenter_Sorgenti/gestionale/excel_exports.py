"""Esportazioni XLSX native: dati tipizzati e testo mai interpretato come formula."""
import io
import json
from datetime import datetime
import analytics
import agreements
import hr
import xlsxwriter
from rules import duration, month_days

MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
KINDS = {'presenze_centro', 'presenze_totali', 'statistiche', 'dipendenti', 'onboarding', 'accordi'}
PRIVATE = {'dipendenti', 'onboarding', 'accordi'}
HR_LABELS = ['Nome', 'Cognome', 'Codice fiscale', 'Data nascita', 'Comune nascita',
 'Cittadinanza', 'Indirizzo', 'CAP', 'Città', 'Provincia', 'Paese', 'Domicilio', 'Email', 'Telefono',
 'Contatto emergenza', 'Telefono emergenza', 'Datore lavoro', 'Reparto', 'Responsabile', 'Contratto',
 'CCNL', 'Livello', 'Qualifica', 'Data ingresso', 'Data fine', 'Fine prova', 'Ore settimanali',
 'Part-time %', 'IBAN', 'Referente paghe', 'Albo professionale', 'Numero iscrizione', 'Scadenza iscrizione',
 'Scadenza permesso lavoro', 'Prossima verifica', 'Note', 'Provincia nascita', 'Tipo documento',
 'Numero documento', 'Ente rilascio', 'Data rilascio', 'Scadenza documento', 'PEC', 'Email aziendale',
 'Partita IVA', 'Modalità pagamento', 'Intestatario conto', 'Banca', 'Numero contratto',
 'Centro costo', 'Sede lavoro', 'Badge', 'Tutor']


def sheet(name, headers, rows, types=None):
    return dict(name=name, headers=headers, rows=rows, types=types or {})


def workbook(title, scope, sheets, notes):
    if sum(len(s['rows']) for s in sheets) > 100000:
        raise ValueError('Esportazione oltre 100.000 righe. Ridurre il periodo o selezionare un centro.')
    stream = io.BytesIO()
    wb = xlsxwriter.Workbook(stream, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
    wb.set_properties({'title': title, 'author': 'Persone e Presenze', 'comments': 'Esportazione del registro; nessuna macro.'})
    formats = {
        'title': wb.add_format({'font_name': 'Calibri', 'font_size': 18, 'font_color': '#233C61', 'bold': True}),
        'scope': wb.add_format({'font_color': '#53677E', 'font_size': 10, 'text_wrap': True, 'valign': 'top'}),
        'header': wb.add_format({'bold': True, 'bg_color': '#233C61', 'font_color': '#FFFFFF', 'text_wrap': True, 'valign': 'vcenter'}),
        'text': wb.add_format({'font_size': 11, 'valign': 'top'}),
        'number': wb.add_format({'num_format': '#,##0', 'font_size': 11, 'valign': 'top'}),
        'decimal': wb.add_format({'num_format': '#,##0.00', 'font_size': 11, 'valign': 'top'}),
        'percent': wb.add_format({'num_format': '0.0%', 'font_size': 11, 'valign': 'top'}),
        'percent_decimal': wb.add_format({'num_format': '0.00%', 'font_size': 11, 'valign': 'top'}),
        'hours': wb.add_format({'num_format': '[h]:mm', 'font_size': 11, 'valign': 'top'}),
        'date': wb.add_format({'num_format': 'dd/mm/yyyy', 'font_size': 11, 'valign': 'top'}),
        'wrap': wb.add_format({'font_size': 11, 'valign': 'top', 'text_wrap': True}),
    }
    all_sheets = sheets + [sheet('Informazioni', ['Voce', 'Dettaglio'],
        [['Esportazione', title], ['Filtri', scope], ['Generata il', datetime.now().astimezone().isoformat(timespec='seconds')]] + notes)]
    for source in all_sheets:
        ws = wb.add_worksheet(source['name']); headers = source['headers']; rows = source['rows']
        last = max(1, len(headers)-1)
        ws.merge_range(0, 0, 0, last, title + ' · ' + source['name'], formats['title'])
        ws.merge_range(1, 0, 1, last, scope, formats['scope']); ws.set_row(0, 30); ws.set_row(1, 32)
        ws.write_row(3, 0, headers, formats['header']); ws.set_row(3, 34)
        for r, values in enumerate(rows, start=4):
            for col, value in enumerate(values):
                kind = source['types'].get(col, 'text'); fmt = formats['wrap'] if source['name']=='Informazioni' else formats.get(kind, formats['text'])
                if value is None or value == '':
                    ws.write_blank(r, col, None, fmt)
                elif kind == 'date':
                    ws.write_datetime(r, col, datetime.fromisoformat(str(value)), fmt)
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    number = value / 1440 if kind == 'hours' else value / 100 if kind in ('percent', 'percent_decimal') else value
                    ws.write_number(r, col, number, fmt if kind != 'text' else formats['number'])
                else:
                    ws.write_string(r, col, str(value), fmt)
        if not rows:
            ws.write_string(4, 0, 'Nessun dato nei filtri selezionati.', formats['scope'])
        for col, label in enumerate(headers):
            lengths = [len(str(v[col] or '')) for v in rows[:100] if col < len(v)]
            width = min(40, max(12, len(label) * .8, max(lengths, default=0) + 2))
            if source['name'] == 'Registro mensile' and 4 <= col < len(headers)-4:
                width = 5
            ws.set_column(col, col, width)
        if source['name'] == 'Informazioni':
            ws.set_column(0, 0, 25); ws.set_column(1, 1, 105, formats['scope'])
        ws.freeze_panes(4, 1); ws.autofilter(3, 0, 3 + len(rows), len(headers)-1)
        ws.set_landscape(); ws.set_paper(9); ws.fit_to_pages(1, 0); ws.repeat_rows(0, 3)
        ws.set_footer('&LPersonale e presenze&C&P / &N'); ws.set_zoom(90)
    wb.close()
    return stream.getvalue()


def metric_sheets(data):
    keys = ['minutes','work_shifts','absence_slots','absence_days','missing_hours','hours_completeness','planned_work','pending_work']
    headers = ['Ore note','Turni effettivi','Assenze (fasce)','Giornate assenza per anagrafica','Turni senza orari','Completezza orari %','Lavoro pianificato (fasce)','Senza consuntivo (fasce)']
    def table(name, leading, rows, extract):
        n = len(leading)
        return sheet(name, leading + headers, [extract(r) + [r[k] for k in keys] for r in rows],
                     {**{i:'number' for i in range(n,len(headers)+n)}, n:'hours', n+5:'percent'})
    return [table('Totali','Periodo'.split(),[data['summary']],lambda r:[data['filters']['first']+' / '+data['filters']['last']]),
            table('Centri',['Centro','Codice'],data['by_center'],lambda r:[r['name'],r['code']]),
            table('Andamento',['Mese'],data['monthly'],lambda r:[r['month']]),
            table('Centro per mese',['Centro','Mese','Chiuso','Calendario verificato'],data['center_months'],lambda r:[r['name'],r['month'],'SI' if r['closed'] else 'NO','SI' if r['verified'] else 'NO']),
            table('Ruoli',['Ruolo alla data'],data['by_role'],lambda r:[r['role']]),
            table('Persone',['Centro','Persona','Ruoli nel periodo'],data['by_person'],lambda r:[r['center'],r['name'],r['role']]),
            sheet('Causali',['Codice','Causale','Assenze (fasce)','Giornate per anagrafica'],[[r['code'],r['label'],r['absence_slots'],r['absence_days']] for r in data['by_cause']],{2:'number',3:'number'})]


def collect(core, user, first, last, cid, role, person_id, private=False):
    months = analytics.months_between(first, last)
    if not isinstance(role,str) or len(role)>100 or not isinstance(person_id,str) or len(person_id)>80:
        raise ValueError('Filtro non valido.')
    if person_id and cid == 'all':
        raise ValueError('Selezionare un centro per esportare una persona.')
    result=[]
    with core.connect() as c:
        c.execute('BEGIN'); user=core.fresh_user(c,user); centers=core.centers_for(c,user)
        if cid!='all':
            core.authorize(user,cid)
            if not any(x['id']==cid for x in centers):raise ValueError('Centro non disponibile.')
            centers=[x for x in centers if x['id']==cid]
        for item in centers:
            center=core.center(c,item['id'])
            if private:core.require_hr(user,center['id'])
            if user['role'] not in ('admin','manager','hr') and not center['config']['operator_export']:
                raise PermissionError('Esportazione non abilitata per tutti i centri selezionati.')
            all_people=core.objects(c,'people',center['id'])
            if person_id and not any(p['id']==person_id for p in all_people):raise ValueError('Persona non disponibile nel centro.')
            # HR exports are a current-state view. Attendance exports use the
            # role recorded for each day, including roles no longer current.
            role_choices=({p['id']:{p['role']} for p in all_people} if private else
                          analytics.period_roles(c,center['id'],all_people,first,last))
            people=[p for p in all_people if (not role or role in role_choices[p['id']]) and (not person_id or p['id']==person_id)]
            ids={p['id'] for p in people}
            entries=[json.loads(r[0]) for r in c.execute("SELECT data FROM entries WHERE cid=? AND json_extract(data,'$.day')>=? AND json_extract(data,'$.day')<=?",(center['id'],first+'-01',month_days(last)[-1]))]
            if any(e['person_id'] not in {p['id'] for p in all_people} for e in entries):raise ValueError('Registrazioni senza anagrafica: correggere l’archivio prima di esportare.')
            entries=[e for e in entries if e['person_id'] in ids]
            effective={} if private else analytics.entry_people(c,center['id'],entries)
            if role and not private:
                entries=[e for e in entries if effective[e['person_id'],e['day']]['role']==role]
            periods={m:core.period(c,center,m) for m in months}
            profiles={};documents={}
            if private:
                profiles={p['id']:hr.profile(c,center['id'],p['id']) for p in people}
                documents={p['id']:hr.docs(c,center['id'],p['id']) for p in people}
            result.append(dict(center=center,people=people,entries=entries,effective=effective,role_choices=role_choices,
                               periods=periods,profiles=profiles,documents=documents,
                               hr_settings=hr.settings(c,center['id']) if private else {}))
    return result


def details(groups):
    rows=[]
    for g in groups:
        people={p['id']:p for p in g['people']}
        for e in sorted(g['entries'],key=lambda e:(e['day'],people[e['person_id']]['name'],e['slot'],e['layer'])):
            p=g['effective'][e['person_id'],e['day']]
            rows.append([g['center']['name'],p['name'],p.get('registration',''),p['role'],e['day'],e['slot'],
                         'Consuntivo' if e['layer']=='actual' else 'Pianificato',e['code'],e['code_label'],e['work_site'],
                         e['start'],e['end'],'SI' if e['overnight'] else 'NO',e['pause'],
                         duration(e) if e['kind']=='work' else None,'SI' if e['holiday'] else 'NO',e.get('note','')])
    return sheet('Dettaglio',['Centro','Dipendente','Matricola','Ruolo alla data','Data','Fascia','Registro','Codice','Causale','Sede effettiva','Ingresso','Uscita','Giorno successivo','Pausa (minuti)','Ore note','Festivo','Note'],rows,{4:'date',13:'number',14:'hours'})


def export(core, user, kind, first, last, cid='all', role='', person_id='', layer='actual'):
    if kind not in KINDS or layer not in ('actual','planned'):raise ValueError('Tipo di esportazione non valido.')
    months=analytics.months_between(first,last)
    if kind in PRIVATE and user['role'] not in ('admin','manager','hr'):raise PermissionError('Prospetto riservato ai ruoli HR autorizzati.')
    if kind=='presenze_centro' and (cid=='all' or first!=last):raise ValueError('Il registro mensile richiede un centro e un solo mese.')
    notes=[['Fonte','Database del gestionale, limitato ai centri autorizzati e ai filtri scelti.'],
           ['Ore','Durata registrata meno pause. Celle vuote indicano ore non disponibili; nessuna stima automatica.'],
           ['Conteggi','Turni e assenze sono fasce. Giornate e persone sono distinte per centro: non sommare i distinti tra viste diverse.'],
           ['Storicità',('Ruolo, anagrafica e fascicolo sono quelli attuali; calendari e accordi sono quelli del mese.'
                         if kind in PRIVATE else analytics.ROLE_HISTORY_NOTE+' Nome e matricola sono quelli attuali.')],
           ['Uso','Copia del registro al momento dell’esportazione. Le modifiche al file non rientrano nel database.']]
    scope=f'Periodo {first} / {last} · '+('Centri autorizzati' if cid=='all' else 'Centro selezionato')+f' · Ruolo: {role or "tutti"}'+(' · Persona selezionata' if person_id else '')
    if kind in ('statistiche','presenze_totali'):
        data=analytics.report(core,user,first,last,cid,role,person_id)
        if not data['export_allowed']:raise PermissionError('Esportazione non abilitata per tutti i centri selezionati.')
        if data['quality']['unmatched_records']:raise ValueError('Registrazioni senza anagrafica: correggere l’archivio prima di esportare.')
        sheets=metric_sheets(data)
        notes.extend([['Assenze %','Assenze / (turni lavorativi + assenze) sulle fasce a consuntivo. Riposi esclusi; non è un tasso contrattuale.'],
                      ['Copertura',f"{data['summary']['missing_hours']} turni senza orari; {data['quality']['closed_months']} mesi-centro chiusi su {data['quality']['center_months']}."]])
        return workbook('Statistiche' if kind=='statistiche' else 'Presenze totali',scope,sheets,notes)
    groups=collect(core,user,first,last,cid,role,person_id,kind in PRIVATE)
    sheets=[]
    if kind=='presenze_centro':
        g=groups[0];cfg=g['periods'][first]['config'];g['entries']=[e for e in g['entries'] if e['layer']==layer]
        slots=[s['id'] for s in cfg['slots'] if s['active']]
        slots+=sorted({e['slot'] for e in g['entries']}-set(slots));labels={s['id']:s['label'] for s in cfg['slots']}
        days=month_days(first);entries={(e['person_id'],e['slot'],e['day']):e for e in g['entries']};rows=[];summary=[]
        for p in g['people']:
            pe=[e for e in g['entries'] if e['person_id']==p['id']]
            if not p['active'] and not pe:continue
            roles={g['effective'][e['person_id'],e['day']]['role'] for e in pe}
            role_label=' / '.join(sorted(roles or ({role} if role else g['role_choices'][p['id']])))
            counts=analytics.empty()
            for e in pe:analytics.add(counts,{**e,'layer':'actual'},g['center'],set())
            totals=analytics.finish(counts)
            summary.append([p['name'],p.get('registration',''),role_label,totals['work_shifts'],totals['absence_slots'],totals['minutes'],totals['missing_hours']])
            for slot in slots:
                es=[e for e in pe if e['slot']==slot];work=[e for e in es if e['kind']=='work'];known=[duration(e) for e in work if duration(e) is not None]
                slot_roles={g['effective'][e['person_id'],e['day']]['role'] for e in es}
                rows.append([p['name'],p.get('registration',''),' / '.join(sorted(slot_roles)) if slot_roles else role_label,labels.get(slot,slot)]+[entries.get((p['id'],slot,d),{}).get('code','') for d in days]+
                    [len(work),sum(e['kind']=='absence' for e in es),sum(known) if known or es and not work else None,len(work)-len(known)])
        sheets=[sheet('Registro mensile',['Dipendente','Matricola','Ruoli nel periodo','Fascia']+[str(int(d[-2:])) for d in days]+['Turni','Assenze','Ore note','Senza orari'],rows,{len(days)+6:'hours'}),
                sheet('Totali persona',['Dipendente','Matricola','Ruoli nel periodo','Turni','Assenze (fasce)','Ore note','Senza orari'],summary,{3:'number',4:'number',5:'hours',6:'number'}),details(groups),
                sheet('Legenda',['Codice','Descrizione','Tipo'],[[c['id'],c['label'],c['kind']] for c in cfg['codes']])]
        scope+=f" · {g['center']['name']} · {'CONSUNTIVO' if layer=='actual' else 'PIANIFICATO'} · Mese {'chiuso' if g['periods'][first]['closed'] else 'aperto'}"
    elif kind=='dipendenti':
        rows=[];custom=[]
        numeric_fields={'weekly_hours':'decimal','part_time_percent':'percent_decimal'}
        for g in groups:
            field_labels={f['id']:f['label'] for f in g['hr_settings']['fields']}
            for p in g['people']:
                profile=g['profiles'][p['id']]
                values=[]
                for k in hr.FIELDS:
                    value=profile['fields'].get(k,'')
                    values.append(float(str(value).replace(',','.')) if k in numeric_fields and value not in ('',None) else value)
                rows.append([g['center']['name'],p['name'],p.get('registration',''),p['role'],'SI' if p['active'] else 'NO',profile['stage']]+values)
                custom.extend([[g['center']['name'],p['name'],k,field_labels.get(k,k),v] for k,v in profile.get('custom',{}).items()])
        field_types={6+i:'date' if k in hr.DATES else numeric_fields[k] for i,k in enumerate(hr.FIELDS) if k in hr.DATES or k in numeric_fields}
        sheets=[sheet('Fascicoli',['Centro','Dipendente','Matricola','Ruolo','Attivo','Stato rapporto']+HR_LABELS,rows,field_types),
                sheet('Campi personalizzati',['Centro','Dipendente','Codice campo','Campo','Valore'],custom)]
        notes.append(['Riservatezza','Fascicoli completi, inclusi dati di identità e pagamento. Accesso riservato ad amministratori, ufficio HR centrale e responsabili dei centri assegnati.'])
    elif kind=='onboarding':
        tasks=[];deadlines=[];documents=[]
        for g in groups:
            for p in g['people']:
                profile=g['profiles'][p['id']];prefix=[g['center']['name'],p['name']]
                tasks.extend([prefix+[t['phase'],t['label'],t['status'],t['owner'],t['due'],t.get('note','')] for t in profile['tasks']])
                deadlines.extend([prefix+[d['label'],d['date'],'SI' if d['late'] else 'NO',d['section']] for d in hr.deadlines(p,profile,g['documents'][p['id']])])
                documents.extend([prefix+[d['category'],d['name'],d['expiry'],d['size'],d['sha256']] for d in g['documents'][p['id']]])
        sheets=[sheet('Attività',['Centro','Dipendente','Fase','Attività','Stato','Responsabile','Scadenza','Note'],tasks,{6:'date'}),
                sheet('Scadenze',['Centro','Dipendente','Scadenza','Data','Superata','Sezione'],deadlines,{3:'date'}),
                sheet('Elenco documenti',['Centro','Dipendente','Categoria','Nome file','Scadenza','Dimensione byte','SHA256'],documents,{4:'date',5:'number'})]
        notes.append(['Ambito HR','Situazione attuale, indipendente dal periodo presenze. Gli allegati non sono incorporati nel file Excel.'])
    elif kind=='accordi':
        rows=[]
        for g in groups:
            for m in months:
                period=g['periods'][m];cfg=core.effective_rules(g['center'],period)
                for p in g['people']:
                    agreement=period.get('agreements',{}).get(p['id'],agreements.proposal(period['config'],p))
                    calc=agreements.calculate(p,g['entries'],m,g['center']['name'],cfg,agreement)
                    rows.append([g['center']['name'],m,p['name'],p['role'],agreement['model'],agreement['basis'],'SI' if agreement['confirmed'] else 'NO',calc['units'],calc['theoretical'],agreement['weekday_rate'],agreement['holiday_rate'],agreement['fixed_deduction'],agreement['fixed_amount'],agreement['adjustment'],calc['amount'],calc['status'],'; '.join(calc['warnings'])])
        sheets=[sheet('Accordi',['Centro','Mese','Dipendente','Ruolo','Modello','Base','Confermato','Unità','Teorico','Tariffa feriale','Tariffa festiva','Detrazione','Quota fissa','Rettifica','Importo calcolato','Stato','Avvertenze'],rows,{i:'decimal' for i in range(7,15)})]
        notes.append(['Importi','Solo accordi confermati e calcolabili generano un importo. Celle vuote non equivalgono a zero. Non sono costo aziendale, contributi o netto in busta.'])
    return workbook({'presenze_centro':'Presenze del centro','dipendenti':'Anagrafiche e fascicoli','onboarding':'Onboarding e scadenze','accordi':'Accordi individuali'}[kind],scope,sheets,notes)
