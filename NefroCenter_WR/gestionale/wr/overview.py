"""Riepilogo di gruppo e lista «Da completare»: sola lettura sui dati autorizzati."""
import csv
import io
from datetime import timedelta

from . import approvals, centers, departures, hr, months, rules, users
from .errors import Forbidden
from .permissions import has, require
from .util import csv_safe, month_days, stamp, today
from . import validate as v
from .web import Reply


def group(db, user, month):
    v.month(month)
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'presenze.vedi')
        rows = []
        for c in centers.visible(con, user):
            if not c['active']:
                continue
            state = months.get(con, c['id'], month)
            persons = months.people(con, c['id'])
            entries = months.entries(con, c['id'], month)
            summary = rules.summarize(persons, entries, today().isoformat())
            wf = approvals.metadata(con, user, c['id'], month)
            last = con.execute('SELECT max(at) FROM audit WHERE center_id=?', (c['id'],)).fetchone()[0]
            rows.append(dict(id=c['id'], name=c['name'], code=c['code'], closed=state['closed'], verified=state['verified'],
                             recorded=bool(entries), people=sum(p['active'] for p in persons),
                             minutes=sum(r['minutes'] for r in summary), shifts=sum(r['shifts'] for r in summary),
                             pending=sum(r['pending'] for r in summary), missing=sum(r['missing'] for r in summary),
                             absences=sum(r['absences'] for r in summary), approval=wf, last_update=last or ''))
    return dict(month=month, centers=rows, generated_at=stamp(),
                totals=dict(centers=len(rows), closed=sum(r['closed'] for r in rows), people=sum(r['people'] for r in rows),
                            shifts=sum(r['shifts'] for r in rows), missing=sum(r['missing'] for r in rows),
                            pending=sum(r['pending'] for r in rows)))


def group_csv(db, user, month):
    with db.read() as con:
        if not has(users.reload(con, user), 'gruppo.riepilogo'):
            raise Forbidden('Riepilogo del gruppo riservato ad amministratore, HR centrale e Direzione.')
    data = group(db, user, month)
    out = io.StringIO()
    writer = csv.writer(out, delimiter=';')
    writer.writerow(['Struttura', 'Codice', 'Mese', 'Stato', 'Presenze compilate', 'Persone attive', 'Minuti lavorati', 'Turni',
                     'Da consuntivare', 'Turni senza orari', 'Approvazione'])
    for r in data['centers']:
        writer.writerow([csv_safe(r['name']), csv_safe(r['code']), month, 'CHIUSO' if r['closed'] else 'APERTO',
                         'SI' if r['recorded'] else 'NO', r['people'], r['minutes'], r['shifts'], r['pending'], r['missing'],
                         r['approval']['label'] if r['approval']['enabled'] else 'Non attiva'])
    return Reply('﻿' + out.getvalue(), content_type='text/csv; charset=utf-8', filename=f'riepilogo_gruppo_{month}.csv')


def todo(db, user, month, center_id='all'):
    """Cose da fare ricavate dai dati: non cambia stati né approvazioni."""
    v.month(month)
    on = today().isoformat()
    horizon = (today() + timedelta(days=30)).isoformat()
    items = []

    def add(category, title, center, person_id='', day='', page='', priority='normal', detail=''):
        items.append(dict(id=str(len(items) + 1), category=category, title=title, center_id=center['id'],
                          center=center['name'], person_id=person_id, day=day, month=month, page=page, priority=priority,
                          detail=detail))

    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'presenze.vedi')
        visible = [c for c in centers.visible(con, user) if c['active']]
        if center_id != 'all':
            centers.scoped(con, user, center_id)
            visible = [c for c in visible if c['id'] == center_id]
        last_day = month_days(month)[-1]
        for c in visible:
            state = months.get(con, c['id'], month)
            names = {p['id']: p for p in months.people(con, c['id'])}
            entries = months.entries(con, c['id'], month)
            actual = {(e['person_id'], e['day'], e['slot']) for e in entries if e['layer'] == 'actual'}
            for e in entries:
                p = names[e['person_id']]
                detail = f'{p["name"]} · {e["day"]} · {e["slot"]}'
                if e['layer'] == 'actual' and e['kind'] == 'work' and rules.duration(e) is None:
                    add('orari', 'Completa gli orari del turno', c, p['id'], e['day'], 'presenze',
                        'urgent' if state['closed'] else 'normal', detail)
                elif (e['layer'] == 'planned' and e['kind'] == 'work' and e['day'] < on
                      and (e['person_id'], e['day'], e['slot']) not in actual):
                    add('consuntivi', 'Registra il consuntivo del turno pianificato', c, p['id'], e['day'], 'presenze',
                        detail=detail)
                if e['review']:
                    add('importazione', 'Verifica una registrazione importata', c, p['id'], e['day'], 'presenze',
                        'urgent', f'{detail} · {e["review"]}')
            if has(user, 'mese.verifica') and not state['verified'] and not state['closed']:
                add('calendario', 'Verifica calendario e parametri del mese', c, page='presenze',
                    detail=f'{month} · verifica del responsabile della struttura')
            if entries and not state['closed'] and last_day < on and has(user, 'mese.chiudi'):
                add('chiusure', 'Controlla e chiudi il mese terminato', c, page='presenze',
                    detail=f'{month} · chiusura dopo i controlli')
            pol = approvals.policy(con, c['id'])
            if pol['enabled']:
                wf = approvals.workflow(con, c['id'], month)
                acts = approvals.available_actions(user, pol, wf, state['closed'], False)
                if any(a in acts for a in ('submit', 'manager_approve', 'hr_approve')) and (wf['status'] != 'draft' or entries):
                    add('approvazioni', 'Approvazione del mese: ' + wf['label'].lower(), c, page='approvazioni',
                        priority='urgent' if wf['status'] in ('submitted', 'manager_approved') else 'normal', detail=month)
            if has(user, 'hr.fascicoli'):
                for p in names.values():
                    if not p['active']:
                        continue
                    prof = hr.profile(con, p['id'])
                    if prof['stage'] == 'ended':
                        continue
                    if not prof['version']:
                        add('fascicoli', 'Compila il fascicolo', c, p['id'], page='persone', detail=p['name'])
                        continue
                    tasks = hr.tasks_of(con, p['id'])
                    progress = hr.progress(tasks, on)
                    if progress['total'] > progress['done']:
                        add('inserimento', 'Completa le attività di inserimento', c, p['id'], page='persone',
                            priority='urgent' if progress['overdue'] else 'normal',
                            detail=f'{p["name"]} · {progress["total"] - progress["done"]} attività aperte')
                    for d in hr.deadlines(p, prof, tasks, hr.documents_meta(con, p['id']), on):
                        if d['date'] <= horizon and d['kind'] != 'attività':
                            add('scadenze', d['label'], c, p['id'], d['date'], 'persone',
                                'urgent' if d['date'] < on else 'normal', p['name'])
            if has(user, 'documenti.verifica'):
                count = con.execute('''SELECT count(*) FROM documents d JOIN document_reviews r ON r.document_id=d.id
                                       WHERE d.center_id=? AND r.status='received' ''', (c['id'],)).fetchone()[0]
                if count:
                    add('documenti', f'Verifica {count} documenti ricevuti', c, page='documenti', detail='Archivio documenti')
            if has(user, 'copertura.decidi'):
                for r in con.execute("SELECT day, slot FROM substitutions WHERE center_id=? AND status='pending' ORDER BY day",
                                     (c['id'],)):
                    add('sostituzioni', 'Valuta una sostituzione proposta', c, day=r['day'], page='copertura',
                        priority='urgent', detail=f'{r["day"]} · fascia {r["slot"]}')
        if has(user, 'uscite.gestisci'):
            names = {c['id']: c for c in visible}
            for case in departures.visible_open_cases(con, user):
                if case['center_id'] in names:
                    open_tasks = sum(t['status'] not in ('done', 'na') for t in case['tasks'])
                    add('uscite', 'Completa il percorso di ' + case['kind_label'].lower(), names[case['center_id']],
                        case['person_id'], case['effective_date'], 'uscite',
                        'urgent' if case['effective_date'] < on else 'normal', f'{open_tasks} attività aperte')
        if has(user, 'backup.gestisci'):
            from . import backups
            problem = backups.last_problem(db)
            if problem:
                add('backup', 'Controlla i backup', dict(id='', name='Server centrale'), page='backup', priority='urgent',
                    detail=problem)
    items.sort(key=lambda x: (x['priority'] != 'urgent', x['day'] or '9999', x['center'], x['title']))
    counts = {}
    for item in items:
        counts[item['category']] = counts.get(item['category'], 0) + 1
    return dict(items=items, counts=counts, total=len(items), urgent=sum(x['priority'] == 'urgent' for x in items),
                month=month, as_of=on, generated_at=stamp(), hr_visible=has(user, 'hr.fascicoli'),
                centers=[dict(id=c['id'], name=c['name']) for c in visible])


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/overview/<month>', cap='presenze.vedi')
def api_group(ctx):
    return group(ctx.db, ctx.user, ctx.params['month'])


@route('GET', '/api/overview/<month>/export.csv', cap='gruppo.riepilogo')
def api_group_csv(ctx):
    return group_csv(ctx.db, ctx.user, ctx.params['month'])


@route('GET', '/api/todo/<month>', cap='presenze.vedi')
def api_todo(ctx):
    return todo(ctx.db, ctx.user, ctx.params['month'], ctx.q('cid', 'all') or 'all')
