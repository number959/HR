"""Statistiche del registro: sola lettura, stessa popolazione per grafici, tabelle ed esportazioni."""
import csv
import io
from collections import defaultdict
from datetime import date, timedelta

from . import centers, hr, months, rules, users
from .errors import Forbidden, Invalid
from .permissions import has, require
from .util import csv_safe, loads, month_days, month_range, stamp, today
from . import validate as v
from .web import Reply

ROLE_NOTE = ('Il ruolo delle registrazioni è quello del contratto valido alla data, se registrato in Personale di gruppo; '
             'altrimenti si usa il ruolo attuale, senza ricostruire lo storico.')


def period(first, last):
    v.month(first, 'Dal mese')
    v.month(last, 'Al mese')
    out = month_range(first, last) if last >= first else []
    if not 1 <= len(out) <= 24:
        raise Invalid('Selezionare un intervallo ordinato di massimo 24 mesi.')
    return out


class Roles:
    """Ruolo valido alla data: contratto registrato, altrimenti ruolo attuale della scheda."""

    def __init__(self, con, persons, first, last):
        self.current = {p['id']: p['role'] for p in persons}
        self.contracts = defaultdict(list)
        ids = list(self.current)
        if ids:
            marks = ','.join('?' * len(ids))
            for r in con.execute(f'''SELECT person_id, valid_from, valid_to, data FROM contracts WHERE person_id IN ({marks})
                                     AND valid_from<=? AND (valid_to='' OR valid_to>=?) ORDER BY valid_from''',
                                 (*ids, last, first)):
                self.contracts[r['person_id']].append((r['valid_from'], r['valid_to'] or '9999-12-31', loads(r['data'])['role']))
        self.first, self.last = first, last

    def on(self, person_id, day):
        for start, end, role in self.contracts[person_id]:
            if start <= day <= end:
                return role, True
        return self.current.get(person_id, ''), False

    def choices(self, person_id):
        """Ruoli disponibili nel periodo per i filtri (anche quelli non più attuali)."""
        roles = {role for _, _, role in self.contracts[person_id]}
        covered = date.fromisoformat(self.first) - timedelta(days=1)
        gap = False
        for start, end, _ in self.contracts[person_id]:
            begin = max(date.fromisoformat(start), date.fromisoformat(self.first))
            if begin > covered + timedelta(days=1):
                gap = True
            covered = max(covered, min(date.fromisoformat(self.last), date.fromisoformat(end)))
        if gap or covered < date.fromisoformat(self.last):
            roles.add(self.current[person_id])
        return roles


def empty():
    return dict(known_minutes=0, work_shifts=0, missing_hours=0, absence_slots=0, rest_slots=0, actual_records=0,
                planned_work=0, pending_work=0, external_shifts=0, festive_shifts=0, people=set(), workdays=set(),
                absence_days=set())


def add(bucket, e, center_id, actual_keys):
    identity = (center_id, e['person_id'])
    bucket['people'].add(identity)
    if e['layer'] == 'planned':
        if e['kind'] == 'work':
            bucket['planned_work'] += 1
            bucket['pending_work'] += (e['person_id'], e['day'], e['slot']) not in actual_keys
        return
    bucket['actual_records'] += 1
    key = (*identity, e['day'])
    if e['kind'] == 'work':
        bucket['work_shifts'] += 1
        minutes = rules.duration(e)
        if minutes is None:
            bucket['missing_hours'] += 1
        else:
            bucket['known_minutes'] += minutes
        bucket['workdays'].add(key)
        bucket['external_shifts'] += bool(e['site'])
        bucket['festive_shifts'] += bool(e['holiday'])
    elif e['kind'] == 'absence':
        bucket['absence_slots'] += 1
        bucket['absence_days'].add(key)
    else:
        bucket['rest_slots'] += 1


def finish(bucket):
    out = {k: val for k, val in bucket.items() if not isinstance(val, set)}
    out['people_count'] = len(bucket['people'])
    out['work_days'] = len(bucket['workdays'])
    out['absence_days'] = len(bucket['absence_days'])
    work = out['work_shifts']
    known = work - out['missing_hours']
    slots = work + out['absence_slots']
    out['known_work_shifts'] = known
    out['hours_completeness'] = round(100 * known / work, 1) if work else None
    out['absence_share'] = round(100 * out['absence_slots'] / slots, 1) if slots else None
    out['minutes'] = out['known_minutes'] if out['actual_records'] and (not work or known) else None
    return out


def _hr_summary(con, persons, role, person_id, on):
    out = dict(active_people=0, missing_profiles=0, onboarding_open=0, tasks_open=0, tasks_overdue=0, deadlines_overdue=0,
               deadlines_next30=0)
    horizon = (date.fromisoformat(on) + timedelta(days=30)).isoformat()
    for p in persons:
        if (role and p['role'] != role) or (person_id and p['id'] != person_id) or not p['active']:
            continue
        prof = hr.profile(con, p['id'])
        if prof['stage'] == 'ended':
            continue
        out['active_people'] += 1
        if not prof['version']:
            out['missing_profiles'] += 1
            continue
        tasks = [t for t in hr.tasks_of(con, p['id']) if t['status'] not in ('done', 'na')]
        out['onboarding_open'] += bool(tasks)
        out['tasks_open'] += len(tasks)
        out['tasks_overdue'] += sum(bool(t['due']) and t['due'] < on for t in tasks)
        dates = [prof['fields'].get(k, '') for k, _, _ in hr.DEADLINE_FIELDS] + [t['due'] for t in tasks]
        dates += [r[0] for r in con.execute('SELECT expiry FROM documents WHERE person_id=?', (p['id'],))]
        out['deadlines_overdue'] += sum(bool(d) and d < on for d in dates)
        out['deadlines_next30'] += sum(bool(d) and on <= d <= horizon for d in dates)
    return out


def report(db, user, first, last, center_id='all', role='', person_id=''):
    periods = period(first, last)
    role = v.text(role, 'Ruolo', 100)
    person_id = v.identifier(person_id, 'Persona', required=False)
    if person_id and center_id == 'all':
        raise Invalid('Selezionare una struttura prima di filtrare una persona.')
    day_first, day_last = first + '-01', month_days(last)[-1]
    on = today().isoformat()
    total, monthly = empty(), {m: empty() for m in periods}
    by_center, by_role, by_cause, by_person, center_months = [], defaultdict(empty), defaultdict(empty), [], []
    roles, options = set(), []
    quality = dict(center_months=0, closed_months=0, verified_months=0, empty_months=0, current_role_fallback_records=0)
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'statistiche.vedi')
        selected_centers = centers.visible(con, user)
        if center_id != 'all':
            centers.scoped(con, user, center_id, 'statistiche.vedi')
            selected_centers = [c for c in selected_centers if c['id'] == center_id]
        hr_visible = has(user, 'hr.fascicoli')
        hr_data = None
        export_allowed = True
        for c in selected_centers:
            current = centers.config(con, c['id'])
            if not has(user, 'presenze.esporta', current):
                export_allowed = False
            persons = months.people(con, c['id'])
            history = Roles(con, persons, day_first, day_last)
            choices = {p['id']: history.choices(p['id']) for p in persons}
            roles.update(r for values in choices.values() for r in values)
            if person_id and not any(p['id'] == person_id for p in persons):
                raise Invalid('Persona non disponibile nella struttura selezionata.')
            matching = [p for p in persons if not role or role in choices[p['id']]]
            if center_id != 'all':
                options.extend(dict(id=p['id'], name=p['name'], role=p['role']) for p in matching)
            chosen = {p['id']: p for p in matching if not person_id or p['id'] == person_id}
            rows = [months.entry_dict(r) for r in con.execute(
                'SELECT * FROM entries WHERE center_id=? AND day BETWEEN ? AND ?', (c['id'], day_first, day_last))]
            rows = [e for e in rows if e['person_id'] in chosen]
            effective = {(e['person_id'], e['day']): history.on(e['person_id'], e['day']) for e in rows}
            rows = [e for e in rows if not role or effective[e['person_id'], e['day']][0] == role]
            quality['current_role_fallback_records'] += sum(not effective[e['person_id'], e['day']][1] for e in rows)
            actual_keys = {(e['person_id'], e['day'], e['slot']) for e in rows if e['layer'] == 'actual'}
            center_bucket, per_month, per_person, person_roles = empty(), {m: empty() for m in periods}, defaultdict(empty), defaultdict(set)
            for e in rows:
                r = effective[e['person_id'], e['day']][0]
                person_roles[e['person_id']].add(r)
                for bucket in (total, monthly[e['day'][:7]], center_bucket, per_month[e['day'][:7]], per_person[e['person_id']],
                               by_role[r]):
                    add(bucket, e, c['id'], actual_keys)
                if e['layer'] == 'actual' and e['kind'] == 'absence':
                    add(by_cause[(e['code'], e['label'])], e, c['id'], actual_keys)
            for m in periods:
                state = months.get(con, c['id'], m)
                record = dict(center_id=c['id'], name=c['name'], code=c['code'], month=m, closed=state['closed'],
                              verified=state['verified'], **finish(per_month[m]))
                center_months.append(record)
                quality['center_months'] += 1
                quality['closed_months'] += record['closed']
                quality['verified_months'] += record['verified']
                quality['empty_months'] += record['actual_records'] == 0
            by_center.append(dict(center_id=c['id'], name=c['name'], code=c['code'], **finish(center_bucket)))
            for pid, bucket in per_person.items():
                by_person.append(dict(center_id=c['id'], center=c['name'], id=pid, name=chosen[pid]['name'],
                                      role=' / '.join(sorted(person_roles[pid])), roles=sorted(person_roles[pid]), **finish(bucket)))
            if hr_visible:
                part = _hr_summary(con, persons, role, person_id, on)
                hr_data = part if hr_data is None else {k: hr_data[k] + part[k] for k in part}
    if hr_data is not None:
        hr_data['as_of'] = on
    return dict(filters=dict(first=first, last=last, center_id=center_id, role=role, person_id=person_id),
                options=dict(roles=sorted(roles), people=sorted(options, key=lambda p: p['name'].casefold())),
                centers=[dict(id=c['id'], name=c['name'], code=c['code']) for c in selected_centers],
                summary=finish(total), monthly=[dict(month=m, **finish(monthly[m])) for m in periods], by_center=by_center,
                by_role=[dict(role=k, **finish(val)) for k, val in sorted(by_role.items())],
                by_cause=[dict(code=k[0], label=k[1], **finish(val)) for k, val in sorted(by_cause.items())],
                by_person=sorted(by_person, key=lambda p: (p['center'].casefold(), p['name'].casefold())),
                center_months=center_months, quality=quality, hr=hr_data, export_allowed=export_allowed, role_note=ROLE_NOTE,
                generated_at=stamp(), has_records=bool(by_person))


def export_csv(db, user, first, last, center_id='all', role='', person_id=''):
    data = report(db, user, first, last, center_id, role, person_id)
    if not data['export_allowed']:
        raise Forbidden('Esportazione non abilitata per tutte le strutture selezionate.')
    out = io.StringIO()
    writer = csv.writer(out, delimiter=';')

    def write(values):
        writer.writerow([csv_safe(x) if isinstance(x, str) else ('' if x is None else x) for x in values])

    write(['Struttura', 'Codice struttura', 'Mese', 'Filtro ruolo', 'Filtro persona (id)', 'Minuti noti', 'Turni effettivi',
           'Turni senza orari', 'Fasce di assenza', 'Giornate di assenza per scheda', 'Riposi', 'Turni fuori sede',
           'Turni festivi', 'Fasce di lavoro pianificate', 'Fasce di lavoro senza consuntivo', 'Completezza orari %',
           'Quota assenze sulle fasce %', 'Mese chiuso', 'Calendario verificato', 'Stato dei dati', 'Storicità del ruolo'])
    for r in data['center_months']:
        status = ('SENZA CONSUNTIVI' if not r['actual_records'] else 'PARZIALI: ORARI MANCANTI' if r['missing_hours']
                  else 'ORARI COMPLETI')
        write([r['name'], r['code'], r['month'], role, person_id, r['minutes'], r['work_shifts'], r['missing_hours'],
               r['absence_slots'], r['absence_days'], r['rest_slots'], r['external_shifts'], r['festive_shifts'],
               r['planned_work'], r['pending_work'], r['hours_completeness'], r['absence_share'],
               'SI' if r['closed'] else 'NO', 'SI' if r['verified'] else 'NO', status, ROLE_NOTE])
    return Reply('﻿' + out.getvalue(), content_type='text/csv; charset=utf-8', filename=f'statistiche_{first}_{last}.csv')


def _args(ctx):
    return dict(first=ctx.q('from'), last=ctx.q('to'), center_id=ctx.q('cid', 'all') or 'all', role=ctx.q('role'),
                person_id=ctx.q('person_id'))


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/statistics', cap='statistiche.vedi')
def api_report(ctx):
    return report(ctx.db, ctx.user, **_args(ctx))


@route('GET', '/api/statistics/export.csv', cap='statistiche.vedi')
def api_csv(ctx):
    return export_csv(ctx.db, ctx.user, **_args(ctx))
