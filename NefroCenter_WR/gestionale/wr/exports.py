"""Prospetti Excel nativi: dati tipizzati, nessuna macro, testo mai interpretato come formula."""
import io
from datetime import datetime

from . import agreements, analytics, audit, centers, hr, months, rules, users
from .errors import Forbidden, Invalid
from .permissions import has, require
from .util import month_days, stamp
from . import validate as v
from .web import Reply

MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
KINDS = {'presenze_centro': 'Presenze della struttura', 'presenze_totali': 'Presenze totali', 'statistiche': 'Statistiche',
         'dipendenti': 'Anagrafiche e fascicoli', 'onboarding': 'Inserimento e scadenze', 'accordi': 'Accordi individuali'}
PRIVATE = {'dipendenti', 'onboarding', 'accordi'}
MAX_ROWS = 100_000


def sheet(name, headers, rows, types=None):
    return dict(name=name, headers=headers, rows=rows, types=types or {})


def workbook(title, scope, sheets, notes):
    import xlsxwriter
    if sum(len(s['rows']) for s in sheets) > MAX_ROWS:
        raise Invalid('Esportazione oltre 100.000 righe: ridurre il periodo o scegliere una struttura.')
    stream = io.BytesIO()
    wb = xlsxwriter.Workbook(stream, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
    wb.set_properties({'title': title, 'author': 'NefroCenter WR', 'comments': 'Esportazione del registro; nessuna macro.'})
    f = {
        'title': wb.add_format({'font_size': 18, 'font_color': '#0b2440', 'bold': True}),
        'scope': wb.add_format({'font_color': '#4a5d73', 'font_size': 10, 'text_wrap': True, 'valign': 'top'}),
        'header': wb.add_format({'bold': True, 'bg_color': '#0b2440', 'font_color': '#ffffff', 'text_wrap': True,
                                 'valign': 'vcenter'}),
        'text': wb.add_format({'valign': 'top'}), 'number': wb.add_format({'num_format': '#,##0', 'valign': 'top'}),
        'decimal': wb.add_format({'num_format': '#,##0.00', 'valign': 'top'}),
        'percent': wb.add_format({'num_format': '0.0%', 'valign': 'top'}),
        'percent_decimal': wb.add_format({'num_format': '0.00%', 'valign': 'top'}),
        'hours': wb.add_format({'num_format': '[h]:mm', 'valign': 'top'}),
        'date': wb.add_format({'num_format': 'dd/mm/yyyy', 'valign': 'top'}),
        'wrap': wb.add_format({'valign': 'top', 'text_wrap': True}),
    }
    info = sheet('Informazioni', ['Voce', 'Dettaglio'], [['Esportazione', title], ['Filtri', scope], ['Generata il', stamp()]] + notes)
    for source in sheets + [info]:
        ws = wb.add_worksheet(source['name'])
        headers, rows = source['headers'], source['rows']
        last = max(1, len(headers) - 1)
        ws.merge_range(0, 0, 0, last, f'{title} · {source["name"]}', f['title'])
        ws.merge_range(1, 0, 1, last, scope, f['scope'])
        ws.set_row(0, 30)
        ws.set_row(1, 32)
        ws.write_row(3, 0, headers, f['header'])
        ws.set_row(3, 34)
        for r, values in enumerate(rows, start=4):
            for col, value in enumerate(values):
                kind = source['types'].get(col, 'text')
                fmt = f['wrap'] if source is info else f.get(kind, f['text'])
                if value is None or value == '':
                    ws.write_blank(r, col, None, fmt)
                elif kind == 'date':
                    ws.write_datetime(r, col, datetime.fromisoformat(str(value)), fmt)
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    number = value / 1440 if kind == 'hours' else value / 100 if kind in ('percent', 'percent_decimal') else value
                    ws.write_number(r, col, number, fmt if kind != 'text' else f['number'])
                else:
                    ws.write_string(r, col, str(value), fmt)
        if not rows:
            ws.write_string(4, 0, 'Nessun dato con i filtri selezionati.', f['scope'])
        for col, label in enumerate(headers):
            lengths = [len(str(row[col] or '')) for row in rows[:100] if col < len(row)]
            width = min(40, max(12, len(label) * .8, max(lengths, default=0) + 2))
            if source['name'] == 'Registro mensile' and 4 <= col < len(headers) - 4:
                width = 5
            ws.set_column(col, col, width)
        if source is info:
            ws.set_column(0, 0, 25)
            ws.set_column(1, 1, 105, f['scope'])
        ws.freeze_panes(4, 1)
        ws.autofilter(3, 0, 3 + len(rows), len(headers) - 1)
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(0, 3)
        ws.set_footer('&LNefroCenter WR&C&P / &N')
        ws.set_zoom(90)
    wb.close()
    return stream.getvalue()


METRIC_KEYS = ['minutes', 'work_shifts', 'absence_slots', 'absence_days', 'missing_hours', 'hours_completeness',
               'planned_work', 'pending_work']
METRIC_HEADERS = ['Ore note', 'Turni effettivi', 'Assenze (fasce)', 'Giornate di assenza per scheda', 'Turni senza orari',
                  'Completezza orari %', 'Lavoro pianificato (fasce)', 'Senza consuntivo (fasce)']


def metric_sheets(data):
    def table(name, leading, rows, extract):
        n = len(leading)
        types = {i: 'number' for i in range(n, n + len(METRIC_HEADERS))}
        types.update({n: 'hours', n + 5: 'percent'})
        return sheet(name, leading + METRIC_HEADERS, [extract(r) + [r[k] for k in METRIC_KEYS] for r in rows], types)

    flt = data['filters']
    return [table('Totali', ['Periodo'], [data['summary']], lambda r: [f'{flt["first"]} / {flt["last"]}']),
            table('Strutture', ['Struttura', 'Codice'], data['by_center'], lambda r: [r['name'], r['code']]),
            table('Andamento', ['Mese'], data['monthly'], lambda r: [r['month']]),
            table('Struttura per mese', ['Struttura', 'Mese', 'Chiuso', 'Calendario verificato'], data['center_months'],
                  lambda r: [r['name'], r['month'], 'SI' if r['closed'] else 'NO', 'SI' if r['verified'] else 'NO']),
            table('Ruoli', ['Ruolo alla data'], data['by_role'], lambda r: [r['role']]),
            table('Persone', ['Struttura', 'Persona', 'Ruoli nel periodo'], data['by_person'],
                  lambda r: [r['center'], r['name'], r['role']]),
            sheet('Causali', ['Codice', 'Causale', 'Assenze (fasce)', 'Giornate per scheda'],
                  [[r['code'], r['label'], r['absence_slots'], r['absence_days']] for r in data['by_cause']], {2: 'number', 3: 'number'})]


def collect(con, user, first, last, center_id, role, person_id, private):
    out = []
    visible = centers.visible(con, user)
    if center_id != 'all':
        centers.scoped(con, user, center_id, 'statistiche.vedi')
        visible = [c for c in visible if c['id'] == center_id]
    day_first, day_last = first + '-01', month_days(last)[-1]
    for c in visible:
        current = centers.config(con, c['id'])
        if private:
            require(user, 'esportazioni.riservate')
        elif not has(user, 'presenze.esporta', current):
            raise Forbidden('Esportazione non abilitata per tutte le strutture selezionate.')
        everyone = months.people(con, c['id'])
        if person_id and not any(p['id'] == person_id for p in everyone):
            raise Invalid('Persona non disponibile nella struttura.')
        history = analytics.Roles(con, everyone, day_first, day_last)
        choices = {p['id']: ({p['role']} if private else history.choices(p['id'])) for p in everyone}
        persons = [p for p in everyone if (not role or role in choices[p['id']]) and (not person_id or p['id'] == person_id)]
        ids = {p['id'] for p in persons}
        entries = [months.entry_dict(r) for r in con.execute('SELECT * FROM entries WHERE center_id=? AND day BETWEEN ? AND ?',
                                                             (c['id'], day_first, day_last)) if r['person_id'] in ids]
        effective = {(e['person_id'], e['day']): history.on(e['person_id'], e['day'])[0] for e in entries}
        if role and not private:
            entries = [e for e in entries if effective[e['person_id'], e['day']] == role]
        out.append(dict(center=c, persons=persons, entries=entries, effective=effective, choices=choices))
    return out


def details(groups):
    rows = []
    for g in groups:
        names = {p['id']: p for p in g['persons']}
        for e in sorted(g['entries'], key=lambda e: (e['day'], names[e['person_id']]['name'], e['slot'], e['layer'])):
            p = names[e['person_id']]
            rows.append([g['center']['name'], p['name'], p['registration'], g['effective'][e['person_id'], e['day']], e['day'],
                         e['slot'], 'Consuntivo' if e['layer'] == 'actual' else 'Pianificato', e['code'], e['label'],
                         e['site'] or g['center']['name'], e['start'], e['end'], 'SI' if e['overnight'] else 'NO', e['pause'],
                         rules.duration(e) if e['kind'] == 'work' else None, 'SI' if e['holiday'] else 'NO', e['note']])
    return sheet('Dettaglio', ['Struttura', 'Dipendente', 'Matricola', 'Ruolo alla data', 'Data', 'Fascia', 'Registro', 'Codice',
                               'Causale', 'Sede effettiva', 'Ingresso', 'Uscita', 'Giorno successivo', 'Pausa (minuti)', 'Ore note',
                               'Festivo', 'Note'], rows, {4: 'date', 13: 'number', 14: 'hours'})


def monthly_grid(con, g, month, layer, role):
    state = months.get(con, g['center']['id'], month)
    cfg, _ = months.configuration(con, g['center']['id'], state)
    entries = [e for e in g['entries'] if e['layer'] == layer]
    slots = [s['id'] for s in cfg['slots'] if s['active']]
    slots += sorted({e['slot'] for e in entries} - set(slots))
    labels = {s['id']: s['label'] for s in cfg['slots']}
    days = month_days(month)
    cells = {(e['person_id'], e['slot'], e['day']): e for e in entries}
    rows, summary = [], []
    for p in g['persons']:
        mine = [e for e in entries if e['person_id'] == p['id']]
        if not p['active'] and not mine:
            continue
        roles = {g['effective'][e['person_id'], e['day']] for e in mine}
        role_label = ' / '.join(sorted(roles or ({role} if role else g['choices'][p['id']])))
        counts = analytics.empty()
        for e in mine:
            analytics.add(counts, dict(e, layer='actual'), g['center']['id'], set())
        totals = analytics.finish(counts)
        summary.append([p['name'], p['registration'], role_label, totals['work_shifts'], totals['absence_slots'], totals['minutes'],
                        totals['missing_hours']])
        for slot in slots:
            here = [e for e in mine if e['slot'] == slot]
            work = [e for e in here if e['kind'] == 'work']
            known = [rules.duration(e) for e in work if rules.duration(e) is not None]
            slot_roles = {g['effective'][e['person_id'], e['day']] for e in here}
            rows.append([p['name'], p['registration'], ' / '.join(sorted(slot_roles)) if slot_roles else role_label,
                         labels.get(slot, slot)] + [cells.get((p['id'], slot, d), {}).get('code', '') for d in days]
                        + [len(work), sum(e['kind'] == 'absence' for e in here),
                           sum(known) if known or (here and not work) else None, len(work) - len(known)])
    grid = sheet('Registro mensile', ['Dipendente', 'Matricola', 'Ruoli nel periodo', 'Fascia'] + [str(int(d[-2:])) for d in days]
                 + ['Turni', 'Assenze', 'Ore note', 'Senza orari'], rows, {len(days) + 6: 'hours'})
    totals_sheet = sheet('Totali per persona', ['Dipendente', 'Matricola', 'Ruoli nel periodo', 'Turni', 'Assenze (fasce)',
                                                'Ore note', 'Senza orari'], summary, {3: 'number', 4: 'number', 5: 'hours', 6: 'number'})
    legend = sheet('Legenda', ['Codice', 'Descrizione', 'Tipo'],
                   [[c['id'], c['label'], {'work': 'Lavoro', 'absence': 'Assenza', 'rest': 'Riposo'}[c['kind']]] for c in cfg['codes']])
    g = dict(g, entries=entries)
    return [grid, totals_sheet, details([g]), legend], state


def export(db, user, kind, first, last, center_id='all', role='', person_id='', layer='actual'):
    kind = v.choice(kind, 'Prospetto', KINDS)
    layer = v.choice(layer, 'Registro', ('actual', 'planned'))
    periods = analytics.period(first, last)
    role = v.text(role, 'Ruolo', 100)
    person_id = v.identifier(person_id, 'Persona', required=False)
    if person_id and center_id == 'all':
        raise Invalid('Selezionare una struttura per esportare una persona.')
    if kind == 'presenze_centro' and (center_id == 'all' or first != last):
        raise Invalid('Il registro mensile richiede una struttura e un solo mese.')
    notes = [['Fonte', 'Archivio del portale, limitato alle strutture autorizzate e ai filtri scelti.'],
             ['Ore', 'Durata registrata meno le pause. Celle vuote: ore non disponibili, nessuna stima automatica.'],
             ['Conteggi', 'Turni e assenze sono fasce. Giornate e persone sono distinte per struttura: non sommare i distinti '
                          'fra viste diverse.'],
             ['Storicità', 'Ruolo, scheda e fascicolo sono quelli attuali; calendari e accordi sono quelli del mese.'
              if kind in PRIVATE else analytics.ROLE_NOTE + ' Nome e matricola sono quelli attuali.'],
             ['Uso', 'Copia del registro al momento dell’esportazione: le modifiche al file non tornano nell’archivio.']]
    scope = (f'Periodo {first} / {last} · ' + ('Strutture autorizzate' if center_id == 'all' else 'Struttura selezionata')
             + f' · Ruolo: {role or "tutti"}' + (' · Persona selezionata' if person_id else ''))
    if kind in ('statistiche', 'presenze_totali'):
        data = analytics.report(db, user, first, last, center_id, role, person_id)
        if not data['export_allowed']:
            raise Forbidden('Esportazione non abilitata per tutte le strutture selezionate.')
        notes += [['Assenze %', 'Assenze / (turni di lavoro + assenze) sulle fasce a consuntivo. Riposi esclusi; non è un tasso '
                                'contrattuale.'],
                  ['Copertura', f'{data["summary"]["missing_hours"]} turni senza orari; {data["quality"]["closed_months"]} '
                                f'mesi-struttura chiusi su {data["quality"]["center_months"]}.']]
        return workbook(KINDS[kind], scope, metric_sheets(data), notes)
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'statistiche.vedi')
        groups = collect(con, user, first, last, center_id, role, person_id, kind in PRIVATE)
        if kind == 'presenze_centro':
            sheets, state = monthly_grid(con, groups[0], first, layer, role)
            scope += (f' · {groups[0]["center"]["name"]} · {"CONSUNTIVO" if layer == "actual" else "PIANIFICATO"} · Mese '
                      f'{"chiuso" if state["closed"] else "aperto"}')
        elif kind == 'dipendenti':
            sheets = _profiles(con, groups)
            notes.append(['Riservatezza', 'Fascicoli completi, inclusi dati di identità e di pagamento. Accesso riservato ad '
                                          'amministratore, HR centrale e responsabili delle strutture assegnate.'])
        elif kind == 'onboarding':
            sheets = _onboarding(con, groups)
            notes.append(['Ambito HR', 'Situazione attuale, indipendente dal periodo delle presenze. Gli allegati non sono inclusi '
                                       'nel file Excel.'])
        else:
            sheets = _agreements(con, groups, periods)
            notes.append(['Importi', 'Solo gli accordi confermati e calcolabili producono un importo. Celle vuote non equivalgono '
                                     'a zero. Non sono costo aziendale, contributi o netto in busta.'])
    return workbook(KINDS[kind], scope, sheets, notes)


def _profiles(con, groups):
    rows, custom = [], []
    numeric = {'weekly_hours': 'decimal', 'part_time_percent': 'percent_decimal'}
    for g in groups:
        labels = {f['id']: f['label'] for f in hr.template(con, g['center']['id'])['fields']}
        for p in g['persons']:
            prof = hr.profile(con, p['id'])
            values = []
            for key in hr.KEYS:
                value = prof['fields'].get(key, '')
                values.append(float(value.replace(',', '.')) if key in numeric and value else value)
            rows.append([g['center']['name'], p['name'], p['registration'], p['role'], 'SI' if p['active'] else 'NO',
                         hr.STAGES[prof['stage']]] + values)
            custom += [[g['center']['name'], p['name'], k, labels.get(k, k), val] for k, val in prof['custom'].items()]
    types = {}
    for i, (key, _, _, _, kind) in enumerate(hr.FIELDS):
        if kind == 'date':
            types[6 + i] = 'date'
        elif key in numeric:
            types[6 + i] = numeric[key]
    return [sheet('Fascicoli', ['Struttura', 'Dipendente', 'Matricola', 'Ruolo', 'Attivo', 'Stato'] + [f[1] for f in hr.FIELDS],
                  rows, types),
            sheet('Campi aggiuntivi', ['Struttura', 'Dipendente', 'Codice campo', 'Campo', 'Valore'], custom)]


def _onboarding(con, groups):
    tasks, deadlines, documents = [], [], []
    for g in groups:
        for p in g['persons']:
            prof = hr.profile(con, p['id'])
            items = hr.tasks_of(con, p['id'])
            docs = hr.documents_meta(con, p['id'])
            prefix = [g['center']['name'], p['name']]
            tasks += [prefix + [t['phase'], t['label'], t['status_label'], t['owner'], t['due'], t['note']] for t in items]
            deadlines += [prefix + [d['label'], d['date'], 'SI' if d['late'] else 'NO', d['section']]
                          for d in hr.deadlines(p, prof, items, docs)]
            documents += [prefix + [d['category'], d['name'], d['expiry'], d['size'], d['sha256'], d['review']['label']] for d in docs]
    return [sheet('Attività', ['Struttura', 'Dipendente', 'Fase', 'Attività', 'Stato', 'Referente', 'Scadenza', 'Note'], tasks, {6: 'date'}),
            sheet('Scadenze', ['Struttura', 'Dipendente', 'Scadenza', 'Data', 'Superata', 'Sezione'], deadlines, {3: 'date'}),
            sheet('Elenco documenti', ['Struttura', 'Dipendente', 'Categoria', 'Nome del file', 'Scadenza', 'Dimensione (byte)',
                                       'SHA256', 'Verifica'], documents, {4: 'date', 5: 'number'})]


def _agreements(con, groups, periods):
    rows = []
    for g in groups:
        for m in periods:
            _, _, results = agreements.month_rows(con, g['center']['id'], m)
            ids = {p['id'] for p in g['persons']}
            for r in results:
                if r['person_id'] not in ids:
                    continue
                a = r['agreement']
                rows.append([g['center']['name'], m, r['name'], r['role'], a['model'], a['basis'], 'SI' if a['confirmed'] else 'NO',
                             r['units'], r['theoretical'], a['weekday_rate'], a['holiday_rate'], a['fixed_deduction'],
                             a['fixed_amount'], a['adjustment'], r['amount'], r['status_label'], '; '.join(r['warnings'])])
    return [sheet('Accordi', ['Struttura', 'Mese', 'Dipendente', 'Ruolo', 'Modello', 'Base', 'Confermato', 'Unità', 'Teorico',
                              'Tariffa feriale', 'Tariffa festiva', 'Detrazione', 'Quota fissa', 'Rettifica', 'Importo calcolato',
                              'Stato', 'Avvertenze'], rows, {i: 'decimal' for i in range(7, 15)})]


def download(db, user, session_recent, args):
    kind = args['kind']
    if kind in PRIVATE:
        with db.read() as con:
            require(users.reload(con, user), 'esportazioni.riservate')
        session_recent()
    data = export(db, user, **args)
    with db.write() as con:
        audit.record(con, users.reload(con, user), 'Esportazione Excel: ' + KINDS[kind].lower(),
                     None if args['center_id'] == 'all' else args['center_id'], entity='export', entity_id=kind,
                     after=dict(kind=kind, first=args['first'], last=args['last'], role=args['role'], person_id=args['person_id']))
    return Reply(data, content_type=MIME, filename=f'{kind}_{args["first"]}_{args["last"]}.xlsx')


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/exports/xlsx', cap='statistiche.vedi')
def api_xlsx(ctx):
    args = dict(kind=ctx.q('kind'), first=ctx.q('from'), last=ctx.q('to'), center_id=ctx.q('cid', 'all') or 'all',
                role=ctx.q('role'), person_id=ctx.q('person_id'), layer=ctx.q('layer', 'actual') or 'actual')
    return download(ctx.db, ctx.user, ctx.recent, args)
