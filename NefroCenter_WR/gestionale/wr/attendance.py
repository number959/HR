"""Registro presenze: consultazione del mese, registrazioni, controlli e chiusura.

Le registrazioni hanno due livelli: 'planned' (turni pianificati) e 'actual'
(consuntivo). Ogni registrazione conserva la versione dei parametri con cui è
stata scritta. Le sovrapposizioni si controllano anche fra strutture diverse
quando le schede appartengono alla stessa identità di gruppo.
"""
import csv
import io

from . import approvals, audit, centers, months, people, rules
from .errors import Conflict, Forbidden, Invalid, NotFound
from .permissions import has
from .util import add_days, csv_safe, new_id, stamp, today_iso
from . import validate as v
from .web import Reply

ENTRY_INPUT = {'id', 'version', 'person_id', 'day', 'slot', 'layer', 'code', 'start', 'end', 'pause', 'overnight',
               'site', 'holiday', 'note'}
CENTER_CAPS = ('presenze.compila', 'presenze.pianifica', 'presenze.orari', 'presenze.sede', 'presenze.festivo',
               'presenze.elimina', 'presenze.esporta', 'presenze.anagrafica', 'presenze.carico', 'mese.verifica',
               'mese.chiudi', 'mese.regole', 'accordi.vedi', 'accordi.modifica', 'approvazioni.vedi')


def efficiency_level(efficiency, cfg):
    """Lettura dell'efficienza come nel vecchio modello (e nel foglio esportato): 'adeguato' se almeno pari alla
    soglia, 'sotto' altrimenti; 'nessuno' quando il rapporto manca perché nessuno era in turno. Un valore
    sopra 1 (carico oltre il riferimento) resta 'adeguato': il modello non prevede una terza lettura."""
    if efficiency is None:
        return 'nessuno'
    return 'sotto' if efficiency < cfg['efficiency_threshold'] else 'adeguato'


def summary_level(efficiency, shifts, cfg):
    """Lettura mensile: distingue il rapporto mancante per assenza di personale ('nessuno') da quello mancante
    perché i pazienti non sono stati registrati nei giorni con turni ('senza_dati')."""
    if efficiency is None and shifts:
        return 'senza_dati'
    return efficiency_level(efficiency, cfg)


def _efficiency(ratio, reference):
    return None if ratio is None or not reference else ratio / reference


def _in_site(entries):
    """Turni a consuntivo svolti nella struttura (le celle senza sfondo colorato del vecchio modello)."""
    return [e for e in entries if e['kind'] == 'work' and e['layer'] == 'actual' and not e['site']]


def workload_rows(con, center_id, month, cfg, persons, entries):
    roles = {p['id']: p['role'] for p in persons}
    in_site = _in_site(entries)
    out = []
    for r in con.execute('SELECT * FROM workload WHERE center_id=? AND day>=? AND day<=? ORDER BY day, slot',
                         (center_id, *months.bounds(month))):
        here = [e for e in in_site if e['day'] == r['day'] and e['slot'] == r['slot']]
        nurses = len({e['person_id'] for e in here if roles.get(e['person_id']) in cfg['nurse_roles']})
        doctors = len({e['person_id'] for e in here if roles.get(e['person_id']) in cfg['doctor_roles']})
        weighted = r['ordinary'] + r['isolated'] * cfg['isolation_weight']
        nurse_ratio = weighted / nurses if nurses else None
        doctor_ratio = (r['ordinary'] + r['isolated']) / doctors if doctors else None
        nurse_efficiency = _efficiency(nurse_ratio, cfg['nurse_reference'])
        doctor_efficiency = _efficiency(doctor_ratio, cfg['doctor_reference'])
        out.append(dict(day=r['day'], slot=r['slot'], ordinary=r['ordinary'], isolated=r['isolated'], nurses=nurses,
                        doctors=doctors, nurse_ratio=nurse_ratio, doctor_ratio=doctor_ratio,
                        nurse_efficiency=nurse_efficiency, doctor_efficiency=doctor_efficiency,
                        nurse_level=efficiency_level(nurse_efficiency, cfg),
                        doctor_level=efficiency_level(doctor_efficiency, cfg),
                        nurse_over=nurse_ratio is not None and nurse_ratio > cfg['nurse_reference'],
                        doctor_over=doctor_ratio is not None and doctor_ratio > cfg['doctor_reference'],
                        uncovered=(r['ordinary'] + r['isolated']) > 0 and (not nurses or not doctors),
                        updated_by=r['updated_by'], updated_at=r['updated_at']))
    return out


def workload_summary(cfg, rows, entries, persons):
    """Sintesi mensile del carico per fascia e complessiva (il blocco di indicatori del vecchio modello).

    rows: righe di workload_rows (giorni con pazienti registrati). I turni si contano su tutte le
    registrazioni di lavoro a consuntivo svolte nella struttura, anche nei giorni senza pazienti
    («Totale turni da lavorare»); i pazienti sommano ordinari e isolati («Totale dialisi da effettuare»).
    Il rapporto mensile di una fascia si calcola sugli stessi giorni al numeratore e al denominatore, come
    nel vecchio modello: pazienti dei giorni con dati / operatori in turno nella sede in quei giorni
    (nurse_rated_shifts, doctor_rated_shifts). Così un mese compilato solo in parte dà una sintesi coerente
    con le righe giornaliere. La «media parametro» è la media dei rapporti delle fasce che li hanno."""
    roles = {p['id']: p['role'] for p in persons}
    in_site = _in_site(entries)
    slots = []
    for slot in cfg['slots']:
        if not slot['active']:
            continue
        mine = [r for r in rows if r['slot'] == slot['id']]
        shifts = [e for e in in_site if e['slot'] == slot['id']]
        nurse_shifts = sum(roles.get(e['person_id']) in cfg['nurse_roles'] for e in shifts)
        doctor_shifts = sum(roles.get(e['person_id']) in cfg['doctor_roles'] for e in shifts)
        nurse_rated = sum(r['nurses'] for r in mine)
        doctor_rated = sum(r['doctors'] for r in mine)
        ordinary = sum(r['ordinary'] for r in mine)
        isolated = sum(r['isolated'] for r in mine)
        nurse_ratio = (ordinary + isolated * cfg['isolation_weight']) / nurse_rated if nurse_rated else None
        doctor_ratio = (ordinary + isolated) / doctor_rated if doctor_rated else None
        nurse_efficiency = _efficiency(nurse_ratio, cfg['nurse_reference'])
        doctor_efficiency = _efficiency(doctor_ratio, cfg['doctor_reference'])
        slots.append(dict(slot=slot['id'], label=slot['label'], days=len(mine), nurse_shifts=nurse_shifts,
                          doctor_shifts=doctor_shifts, nurse_rated_shifts=nurse_rated, doctor_rated_shifts=doctor_rated,
                          ordinary=ordinary, isolated=isolated, patients=ordinary + isolated,
                          nurse_ratio=nurse_ratio, doctor_ratio=doctor_ratio, nurse_efficiency=nurse_efficiency,
                          doctor_efficiency=doctor_efficiency, nurse_level=summary_level(nurse_efficiency, nurse_shifts, cfg),
                          doctor_level=summary_level(doctor_efficiency, doctor_shifts, cfg)))

    def average(values):
        values = [x for x in values if x is not None]
        return sum(values) / len(values) if values else None

    nurse_parameter = average(s['nurse_ratio'] for s in slots)
    doctor_parameter = average(s['doctor_ratio'] for s in slots)
    nurse_efficiency = _efficiency(nurse_parameter, cfg['nurse_reference'])
    doctor_efficiency = _efficiency(doctor_parameter, cfg['doctor_reference'])
    nurse_shifts = sum(s['nurse_shifts'] for s in slots)
    doctor_shifts = sum(s['doctor_shifts'] for s in slots)
    return dict(slots=slots, nurse_shifts=nurse_shifts, doctor_shifts=doctor_shifts,
                nurse_rated_shifts=sum(s['nurse_rated_shifts'] for s in slots),
                doctor_rated_shifts=sum(s['doctor_rated_shifts'] for s in slots),
                ordinary=sum(s['ordinary'] for s in slots), isolated=sum(s['isolated'] for s in slots),
                patients=sum(s['patients'] for s in slots), days=len({r['day'] for r in rows}),
                nurse_parameter=nurse_parameter, doctor_parameter=doctor_parameter,
                nurse_efficiency=nurse_efficiency, doctor_efficiency=doctor_efficiency,
                nurse_level=summary_level(nurse_efficiency, nurse_shifts, cfg),
                doctor_level=summary_level(doctor_efficiency, doctor_shifts, cfg),
                threshold=cfg['efficiency_threshold'], nurse_reference=cfg['nurse_reference'],
                doctor_reference=cfg['doctor_reference'], isolation_weight=cfg['isolation_weight'],
                dialysis_stations=cfg['dialysis_stations'], isolation_stations=cfg['isolation_stations'])


COUNTER_GROUPS = (('infermieri', 'Infermieri'), ('medici', 'Medici'), ('altro', 'Altro personale'))
COUNTER_KEYS = ('shifts', 'external', 'festive', 'absences', 'total', 'registrations')
# Il «totale registrazioni» del vecchio modello esclude i recuperi turno (formula «− RC»); i riposi, che il
# modello non aveva, restano fuori allo stesso modo. È la stessa base della proposta di accordo (agreements.proposal).
NOT_IN_TOTAL = ('RC',)


def counters(cfg, summary):
    """Conteggi del mese per persona e per gruppo (i contatori a destra della griglia del vecchio modello).

    Per ogni persona: turni, fuori sede, festivi, una voce per ogni causale di assenza o riposo dei
    parametri (0 se non usata), totale come nel modello (registrazioni a consuntivo senza recuperi turno
    e riposi) e registrazioni (tutte le registrazioni a consuntivo). I gruppi seguono i ruoli
    infermieristici e medici dei parametri; le persone non attive senza registrazioni restano fuori."""
    used = {c for row in summary for c in row['causes']}
    codes = [dict(id=c['id'], label=c['label']) for c in cfg['codes']
             if c['kind'] != 'work' and (c['active'] or c['id'] in used)]
    code_ids = [c['id'] for c in codes]
    excluded = set(NOT_IN_TOTAL) | {c['id'] for c in cfg['codes'] if c['kind'] == 'rest'}
    people_rows = []
    for row in summary:
        registrations = sum(row['causes'].values())
        total = sum(n for code, n in row['causes'].items() if code not in excluded)
        if not row['active'] and not registrations:
            continue
        group = ('infermieri' if row['role'] in cfg['nurse_roles'] else 'medici' if row['role'] in cfg['doctor_roles'] else 'altro')
        people_rows.append(dict(person_id=row['person_id'], name=row['name'], role=row['role'],
                                registration=row['registration'], active=row['active'], group=group,
                                shifts=row['shifts'], external=row['external'], festive=row['festive'],
                                absences=row['absences'], codes={c: row['causes'].get(c, 0) for c in code_ids},
                                total=total, registrations=registrations))

    def totals(label, group_id, members):
        out = dict(id=group_id, label=label, people=len(members))
        out.update({k: sum(m[k] for m in members) for k in COUNTER_KEYS})
        out['codes'] = {c: sum(m['codes'][c] for m in members) for c in code_ids}
        return out

    groups = [totals(label, gid, [m for m in people_rows if m['group'] == gid]) for gid, label in COUNTER_GROUPS]
    groups = [g for g in groups if g['people']]
    groups.append(totals('Tutto il personale', 'tutti', people_rows))
    return dict(codes=codes, people=people_rows, groups=groups)


def alerts_for(state, summary, entries, approval):
    out = []
    if approval['stale']:
        out.append(dict(level='warning', text='I dati sono cambiati dopo l’invio in approvazione: il mese va restituito e inviato di nuovo.'))
    if not state['verified'] and not state['closed']:
        out.append(dict(level='info', text='Calendario e parametri del mese da verificare dal responsabile della struttura.'))
    for row in summary:
        if row['missing']:
            out.append(dict(level='warning', text=f'{row["name"]}: {row["missing"]} turni senza orari.', person_id=row['person_id']))
        if row['pending']:
            out.append(dict(level='warning', text=f'{row["name"]}: {row["pending"]} fasce pianificate da consuntivare.',
                            person_id=row['person_id']))
    review = sum(bool(e['review']) for e in entries)
    if review:
        out.append(dict(level='warning', text=f'{review} registrazioni importate da verificare (sede o dati non riconosciuti).'))
    return out


def snapshot(db, user, center_id, month):
    v.month(month)
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'presenze.vedi')
        state = months.get(con, center_id, month)
        cfg, current = months.configuration(con, center_id, state)
        persons = months.people(con, center_id)
        entries = months.entries(con, center_id, month)
        summary = rules.summarize(persons, entries, today_iso())
        approval = approvals.metadata(con, user, center_id, month)
        caps = {cap: has(user, cap, current) for cap in CENTER_CAPS}
        editable = caps['presenze.compila'] and not state['closed'] and not approval['frozen']
        known = [r[0] for r in con.execute('SELECT month FROM months WHERE center_id=? ORDER BY month DESC LIMIT 36',
                                           (center_id,))]
        days = months.days_info(month, cfg)
        workload = workload_rows(con, center_id, month, cfg, persons, entries) if caps['presenze.carico'] else []
        result = dict(
            center=dict(id=center['id'], name=center['name'], code=center['code'], config_version=center['config_version']),
            month=month, state={k: state[k] for k in ('rules_version', 'verified', 'closed', 'note', 'version',
                                                      'updated_at', 'updated_by', 'stored')},
            rules_outdated=state['rules_version'] != center['config_version'],
            config=cfg, days=days, working_days=sum(d['working'] for d in days),
            people=[people.public(p, user) for p in persons], entries=entries, summary=summary,
            workload=workload,
            workload_summary=workload_summary(cfg, workload, entries, persons) if caps['presenze.carico'] else None,
            counters=counters(cfg, summary),
            approval=approval, alerts=alerts_for(state, summary, entries, approval), caps=caps, editable=editable,
            known_months=known, history=audit.recent(con, center_id, 40))
    return result


def _linked(con, center_id, person, day):
    """Registrazioni della stessa identità nei giorni vicini, anche in altre strutture."""
    rows = con.execute('''SELECT e.*, c.name AS center_name FROM entries e JOIN people p ON p.id=e.person_id
                          JOIN centers c ON c.id=e.center_id WHERE p.identity_id=? AND e.day BETWEEN ? AND ?''',
                       (person['identity_id'], add_days(day, -3), add_days(day, 3)))
    out = []
    for r in rows:
        item = months.entry_dict(r)
        item['center_name'] = r['center_name'] if r['center_id'] != center_id else ''
        out.append(item)
    return out


def _entry(con, center_id, month, entry_id):
    found = con.execute('SELECT * FROM entries WHERE id=? AND center_id=? AND day LIKE ?',
                        (entry_id, center_id, month + '-%')).fetchone()
    if not found:
        raise NotFound('Registrazione non trovata nel mese: ricaricare.')
    return months.entry_dict(found)


def _writable(con, actor, center_id, month):
    state = months.get(con, center_id, month)
    months.require_open(state)
    approvals.guard_month(con, actor, center_id, month)
    return state


def save_entry(db, actor, center_id, month, raw):
    v.month(month)
    v.keys(raw, ENTRY_INPUT, 'Registrazione', required={'person_id', 'day', 'slot', 'layer', 'code'})
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'presenze.compila')
        state = _writable(con, actor, center_id, month)
        cfg, current = months.configuration(con, center_id, state)
        person = people.get(con, center_id, v.identifier(raw['person_id'], 'Persona'))
        old = None
        if raw.get('id'):
            old = _entry(con, center_id, month, v.identifier(raw['id'], 'Registrazione'))
            if v.version(raw.get('version')) != old['version']:
                raise Conflict('Registrazione modificata da un’altra sessione: ricaricare.')
            if old['person_id'] != person['id']:
                raise Invalid('Per spostare una registrazione eliminarla e inserirla di nuovo.', field='person_id')
        elif not person['active']:
            raise Invalid('Persona non attiva: riattivarla nell’anagrafica prima di registrare presenze.', field='person_id')
        if old and old['layer'] == 'planned' and not has(actor, 'presenze.pianifica', current):
            raise Forbidden('Pianificazione riservata al responsabile della struttura e all’amministratore.')

        def can(cap):
            return has(actor, cap, current)

        entry = rules.build_entry(raw, config=cfg, person=person, month=month, can=can, old=old)
        entry['id'] = old['id'] if old else new_id()
        warnings = rules.check_conflicts(entry, _linked(con, center_id, person, entry['day']), cfg['min_rest_hours'])
        if entry['kind'] == 'work' and not entry['start']:
            warnings.append('Turno registrato senza orari: le ore non vengono calcolate.')
        state = months.ensure(con, center_id, month, actor)
        values = (entry['code'], entry['kind'], entry['label'], entry['start'], entry['end'], entry['pause'],
                  int(entry['overnight']), entry['site'], int(entry['holiday']), entry['credit'], entry['note'])
        review = rules.IMPORT_SITE_REVIEW if entry['site'] == rules.IMPORT_SITE else ''
        if old:
            con.execute('''UPDATE entries SET code=?, kind=?, label=?, start=?, end=?, pause=?, overnight=?, site=?, holiday=?,
                           credit=?, note=?, review=?, version=version+1, updated_at=?, updated_by=? WHERE id=?''',
                        (*values, review, stamp(), actor.username, old['id']))
        else:
            con.execute('''INSERT INTO entries(code,kind,label,start,end,pause,overnight,site,holiday,credit,note,id,center_id,
                           person_id,day,slot,layer,source,rules_version,version,updated_at,updated_by)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)''',
                        (*values, entry['id'], center_id, person['id'], entry['day'], entry['slot'], entry['layer'],
                         'manuale', state['rules_version'], stamp(), actor.username))
        saved = _entry(con, center_id, month, entry['id'])
        audit.record(con, actor, 'Registrazione modificata' if old else 'Registrazione inserita', center_id,
                     entity='entry', entity_id=entry['id'], before=_brief(old) if old else None, after=_brief(saved))
    return dict(entry=saved, warnings=list(dict.fromkeys(warnings)))


def _brief(e):
    return {k: e[k] for k in ('person_id', 'day', 'slot', 'layer', 'code', 'start', 'end', 'pause', 'overnight', 'site',
                              'holiday', 'note')}


def delete_entry(db, actor, center_id, month, entry_id, raw):
    v.month(month)
    v.keys(raw, {'version'}, 'Eliminazione', required={'version'})
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'presenze.compila')
        _writable(con, actor, center_id, month)
        current = centers.config(con, center_id)
        old = _entry(con, center_id, month, v.identifier(entry_id, 'Registrazione'))
        if v.version(raw['version']) != old['version']:
            raise Conflict('Registrazione modificata da un’altra sessione: ricaricare.')
        if not has(actor, 'presenze.elimina', current):
            raise Forbidden('Eliminazione riservata al responsabile della struttura e all’amministratore.')
        if old['layer'] == 'planned' and not has(actor, 'presenze.pianifica', current):
            raise Forbidden('Pianificazione riservata al responsabile della struttura e all’amministratore.')
        if con.execute("SELECT 1 FROM substitutions WHERE entry_id=? AND status='accepted'", (old['id'],)).fetchone():
            raise Invalid('Turno nato da una sostituzione accettata: correggerlo invece di eliminarlo, '
                          'oppure annotare la variazione.')
        con.execute('DELETE FROM entries WHERE id=?', (old['id'],))
        audit.record(con, actor, 'Registrazione eliminata', center_id, entity='entry', entity_id=old['id'], before=_brief(old))
    return dict(ok=True)


def verify_month(db, actor, center_id, month, raw):
    v.month(month)
    v.keys(raw, {'verified', 'note', 'version'}, 'Verifica del mese', required={'verified', 'version'})
    verified = v.boolean(raw['verified'], 'Calendario verificato', field='verified')
    note = v.text(raw.get('note', ''), 'Nota', 2000, multiline=True, field='note')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'mese.verifica')
        state = _writable(con, actor, center_id, month)
        months.check_version(state, raw['version'])
        state = months.update(con, center_id, month, actor, verified=verified, note=note)
        audit.record(con, actor, 'Calendario e parametri ' + ('verificati' if verified else 'da verificare'), center_id,
                     entity='month', entity_id=month, after=dict(verified=verified, note=note))
    return dict(state=state)


def close_month(db, actor, center_id, month, raw):
    v.month(month)
    v.keys(raw, {'version'}, 'Chiusura', required={'version'})
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'mese.chiudi')
        state = months.get(con, center_id, month)
        months.require_open(state)
        approvals.guard_month(con, actor, center_id, month, 'close')
        months.check_version(state, raw['version'])
        problems = months.close_checks(con, center_id, month)
        if problems:
            raise Invalid(' '.join(problems))
        state = months.update(con, center_id, month, actor, closed=True)
        audit.record(con, actor, 'Mese chiuso', center_id, entity='month', entity_id=month)
    return dict(state=state)


def reopen_month(db, actor, center_id, month, raw):
    v.month(month)
    v.keys(raw, {'version', 'reason'}, 'Riapertura', required={'version', 'reason'})
    reason = v.reason(raw['reason'])
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'mese.chiudi')
        state = months.get(con, center_id, month)
        if not state['closed']:
            raise Invalid('Il mese è già aperto.')
        months.check_version(state, raw['version'])
        approvals.guard_month(con, actor, center_id, month, 'reopen', reason)
        state = months.update(con, center_id, month, actor, closed=False, note=reason)
        audit.record(con, actor, 'Mese riaperto', center_id, entity='month', entity_id=month, after=dict(reason=reason))
    return dict(state=state)


def apply_rules(db, actor, center_id, month, raw):
    v.month(month)
    v.keys(raw, {'version', 'reason'}, 'Nuovi parametri', required={'version', 'reason'})
    reason = v.reason(raw['reason'])
    with db.write() as con:
        actor, center = centers.scoped(con, actor, center_id, 'mese.regole')
        state = _writable(con, actor, center_id, month)
        months.check_version(state, raw['version'])
        if con.execute('SELECT 1 FROM entries WHERE center_id=? AND day>=? AND day<=? LIMIT 1',
                       (center_id, *months.bounds(month))).fetchone():
            raise Invalid('Il mese contiene registrazioni: per conservare lo storico i nuovi parametri valgono dai mesi '
                          'non ancora compilati.')
        before = state['rules_version']
        state = months.update(con, center_id, month, actor, rules_version=center['config_version'], verified=False, note=reason)
        audit.record(con, actor, 'Parametri più recenti applicati al mese', center_id, entity='month', entity_id=month,
                     before=dict(rules_version=before), after=dict(rules_version=center['config_version'], reason=reason))
    return dict(state=state)


def save_workload(db, actor, center_id, month, raw):
    v.month(month)
    v.keys(raw, {'day', 'slot', 'ordinary', 'isolated'}, 'Pazienti', required={'day', 'slot', 'ordinary', 'isolated'})
    day = v.day(raw['day'], field='day')
    if not day.startswith(month + '-'):
        raise Invalid('Data fuori dal mese selezionato.', field='day')
    ordinary = v.integer(raw['ordinary'], 'Pazienti', 0, 10000, field='ordinary')
    isolated = v.integer(raw['isolated'], 'Pazienti in isolamento', 0, 10000, field='isolated')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'presenze.carico')
        state = _writable(con, actor, center_id, month)
        cfg, _ = months.configuration(con, center_id, state)
        slot = v.choice(raw['slot'], 'Fascia', {s['id'] for s in cfg['slots']}, field='slot')
        months.ensure(con, center_id, month, actor)
        before = con.execute('SELECT ordinary, isolated FROM workload WHERE center_id=? AND day=? AND slot=?',
                             (center_id, day, slot)).fetchone()
        con.execute('''INSERT INTO workload(center_id,day,slot,ordinary,isolated,updated_at,updated_by) VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(center_id,day,slot) DO UPDATE SET ordinary=excluded.ordinary, isolated=excluded.isolated,
                       updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (center_id, day, slot, ordinary, isolated, stamp(), actor.username))
        audit.record(con, actor, 'Pazienti per fascia registrati', center_id, entity='workload', entity_id=f'{day}|{slot}',
                     before=dict(before) if before else None, after=dict(ordinary=ordinary, isolated=isolated))
    return dict(ok=True)


def export_csv(db, user, center_id, month, detail=False):
    v.month(month)
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'presenze.vedi')
        current = centers.config(con, center_id)
        if not has(user, 'presenze.esporta', current):
            raise Forbidden('Esportazione del registro non consentita a questo profilo dai parametri della struttura.')
        state = months.get(con, center_id, month)
        cfg, _ = months.configuration(con, center_id, state)
        persons = months.people(con, center_id)
        entries = months.entries(con, center_id, month)
    status = 'CHIUSO' if state['closed'] else 'BOZZA'
    out = io.StringIO()
    writer = csv.writer(out, delimiter=cfg['csv_separator'])

    def row(values):
        writer.writerow([csv_safe(x) if isinstance(x, str) else x for x in values])

    by_id = {p['id']: p for p in persons}
    if detail:
        row(['Stato', 'Struttura', 'Matricola', 'Persona', 'Data', 'Fascia', 'Causale', 'Registro', 'Sede', 'Ingresso', 'Uscita',
             'Giorno successivo', 'Pausa min', 'Minuti lavorati', 'Festivo', 'Versione parametri', 'Operatore', 'Note'])
        for e in sorted(entries, key=lambda e: (e['day'], by_id[e['person_id']]['name'].casefold(), e['slot'])):
            p = by_id[e['person_id']]
            minutes = rules.duration(e)
            row([status, center['name'], p['registration'], p['name'], e['day'], e['slot'], e['code'],
                 'Consuntivo' if e['layer'] == 'actual' else 'Pianificato', e['site'] or center['name'], e['start'], e['end'],
                 int(e['overnight']), e['pause'], '' if minutes is None else minutes, int(e['holiday']), e['rules_version'],
                 e['updated_by'], e['note']])
    else:
        summary = rules.summarize(persons, entries, today_iso())
        causes = sorted({c for r in summary for c in r['causes']})
        row(['Stato', 'Struttura', 'Mese', 'Matricola', 'Persona', 'Ruolo', 'Turni', 'Giorni', 'Minuti lavorati con orari',
             'Turni senza orario', 'Fasce di assenza', 'Credito assenze min', 'Fuori sede', 'Festivi', 'Da consuntivare'] + causes)
        for r in summary:
            row([status, center['name'], month, r['registration'], r['name'], r['role'], r['shifts'], r['days'], r['minutes'],
                 r['missing'], r['absences'], r['credit'], r['external'], r['festive'], r['pending']]
                + [r['causes'].get(c, 0) for c in causes])
    name = f'presenze_{center["code"]}_{month}{"_dettaglio" if detail else ""}.csv'
    return Reply('﻿' + out.getvalue(), content_type='text/csv; charset=utf-8', filename=name)


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402

BASE = '/api/attendance/<cid>/<month>'


@route('GET', BASE, cap='presenze.vedi')
def api_snapshot(ctx):
    return snapshot(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'])


@route('POST', BASE + '/entries', cap='presenze.compila')
def api_save(ctx):
    return save_entry(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.body)


@route('DELETE', BASE + '/entries/<entry_id>', cap='presenze.compila')
def api_delete(ctx):
    return delete_entry(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.params['entry_id'], ctx.body)


@route('POST', BASE + '/verify', cap='mese.verifica')
def api_verify(ctx):
    return verify_month(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.body)


@route('POST', BASE + '/close', cap='mese.chiudi')
def api_close(ctx):
    return close_month(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.body)


@route('POST', BASE + '/reopen', cap='mese.chiudi')
def api_reopen(ctx):
    return reopen_month(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.body)


@route('POST', BASE + '/apply-rules', cap='mese.regole')
def api_apply(ctx):
    return apply_rules(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.body)


@route('PUT', BASE + '/workload', cap='presenze.carico')
def api_workload(ctx):
    return save_workload(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.body)


@route('GET', BASE + '/export.csv', cap='presenze.vedi')
def api_export(ctx):
    return export_csv(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.q('detail') == '1')
