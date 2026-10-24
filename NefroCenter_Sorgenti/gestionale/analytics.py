"""Statistiche del registro: sola lettura, stessa popolazione per grafici ed export."""
import csv
import io
import json
import re
import workforce
from collections import defaultdict
from datetime import date, timedelta
from rules import duration, month_days

ROLE_HISTORY_NOTE = ('Il ruolo delle registrazioni è quello valido alla data, se presente nelle decorrenze. '
                     'In assenza di una decorrenza registrata si usa il ruolo attuale, senza ricostruire lo storico. '
                     'Le correzioni esplicite delle decorrenze si riflettono anche nei report di mesi chiusi.')


def period_roles(c, cid, people, first, last):
    """Roles available for filters, including recorded roles no longer current."""
    result = {p['id']: set() for p in people}
    start, end = date.fromisoformat(first+'-01').toordinal(), date.fromisoformat(month_days(last)[-1]).toordinal()
    covered_until = {p['id']: start-1 for p in people}
    fallback = set()
    for row in c.execute('''SELECT pid,data FROM workforce_contracts WHERE cid=?
            AND effective_from<=? AND (effective_to='' OR effective_to>=?) ORDER BY effective_from''',
            (cid, month_days(last)[-1], first+'-01')):
        if row['pid'] in result:
            result[row['pid']].add(json.loads(row['data'])['role'])
    # A current role is only a fallback on dates not covered by a recorded contract.
    for row in c.execute('''SELECT pid,effective_from,effective_to FROM workforce_contracts WHERE cid=?
            AND effective_from<=? AND (effective_to='' OR effective_to>=?) ORDER BY effective_from''',
            (cid, month_days(last)[-1], first+'-01')):
        pid = row['pid']
        if pid not in result:
            continue
        if max(start, date.fromisoformat(row['effective_from']).toordinal()) > covered_until[pid]+1:
            fallback.add(pid)
        covered_until[pid] = max(covered_until[pid], min(end, date.fromisoformat(row['effective_to']).toordinal()) if row['effective_to'] else end)
    for p in people:
        if p['id'] in fallback or covered_until[p['id']] < end:
            result[p['id']].add(p['role'])
    return result


def entry_people(c, cid, entries):
    """One date-effective lookup per person/day, shared by planned and actual."""
    return {(pid, day): workforce.effective_person(c, cid, pid, day)
            for pid, day in {(e['person_id'], e['day']) for e in entries}}


def months_between(first, last):
    if not all(isinstance(x, str) and re.fullmatch(r'\d{4}-\d{2}', x) for x in (first, last)):
        raise ValueError('Indicare mese iniziale e finale nel formato AAAA-MM.')
    month_days(first); month_days(last)
    start = int(first[:4]) * 12 + int(first[5:]) - 1
    end = int(last[:4]) * 12 + int(last[5:]) - 1
    if not 0 <= end - start < 24:
        raise ValueError('Selezionare un intervallo ordinato di massimo 24 mesi.')
    return [f'{n // 12:04d}-{n % 12 + 1:02d}' for n in range(start, end + 1)]


def empty():
    return dict(known_minutes=0, work_shifts=0, missing_hours=0, absence_slots=0,
                rest_slots=0, actual_records=0, planned_work=0, pending_work=0,
                external_shifts=0, festive_shifts=0, people=set(), workdays=set(),
                absence_days=set())


def add(bucket, entry, center, actual_keys):
    identity = (center['id'], entry['person_id'])
    bucket['people'].add(identity)
    if entry['layer'] == 'planned':
        if entry['kind'] == 'work':
            bucket['planned_work'] += 1
            bucket['pending_work'] += (entry['person_id'], entry['day'], entry['slot']) not in actual_keys
        return
    bucket['actual_records'] += 1
    daykey = (*identity, entry['day'])
    if entry['kind'] == 'work':
        bucket['work_shifts'] += 1
        minutes = duration(entry)
        if minutes is None:
            bucket['missing_hours'] += 1
        else:
            bucket['known_minutes'] += minutes
        bucket['workdays'].add(daykey)
        bucket['external_shifts'] += entry['work_site'] != center['name']
        bucket['festive_shifts'] += bool(entry['holiday'])
    elif entry['kind'] == 'absence':
        bucket['absence_slots'] += 1
        bucket['absence_days'].add(daykey)
    elif entry['kind'] == 'rest':
        bucket['rest_slots'] += 1


def finish(bucket):
    out = {k: v for k, v in bucket.items() if not isinstance(v, set)}
    out['people_count'] = len(bucket['people'])
    out['work_days'] = len(bucket['workdays'])
    out['absence_days'] = len(bucket['absence_days'])
    work = out['work_shifts']; known = work - out['missing_hours']
    denominator = work + out['absence_slots']
    out['known_work_shifts'] = known
    out['hours_completeness'] = round(100 * known / work, 1) if work else None
    out['absence_share'] = round(100 * out['absence_slots'] / denominator, 1) if denominator else None
    out['minutes'] = out['known_minutes'] if out['actual_records'] and (not work or known) else None
    return out


def hr_summary():
    return dict(active_people=0, missing_profiles=0, onboarding_open=0, tasks_open=0,
                tasks_overdue=0, deadlines_overdue=0, deadlines_next30=0)


def include_hr(out, person, profile, documents, today):
    if not person['active'] or (profile and profile.get('stage') == 'ended'):
        return
    out['active_people'] += 1
    if profile is None:
        out['missing_profiles'] += 1
        return
    first = today.isoformat(); last = (today + timedelta(days=30)).isoformat()
    tasks = [t for t in profile.get('tasks', []) if t['status'] not in ('done', 'na')]
    out['onboarding_open'] += bool(tasks)
    out['tasks_open'] += len(tasks)
    out['tasks_overdue'] += sum(bool(t.get('due')) and t['due'] < first for t in tasks)
    fields = profile.get('fields', {})
    deadlines = [fields.get(k, '') for k in ('identity_expiry', 'end_date', 'probation_end',
                 'registration_expiry', 'work_permit_expiry', 'next_review')]
    deadlines += [t.get('due', '') for t in tasks] + [d['expiry'] for d in documents]
    out['deadlines_overdue'] += sum(bool(d) and d < first for d in deadlines)
    out['deadlines_next30'] += sum(bool(d) and first <= d <= last for d in deadlines)


def report(core, user, first, last, cid='all', role='', person_id='', today=None):
    months = months_between(first, last)
    if not isinstance(role, str) or len(role) > 100 or not isinstance(person_id, str) or len(person_id) > 80:
        raise ValueError('Filtro non valido.')
    if person_id and cid == 'all':
        raise ValueError('Selezionare un centro prima di filtrare una persona.')
    today = today or date.today()
    total = empty(); monthly = {m: empty() for m in months}
    by_center = []; by_role = defaultdict(empty); by_cause = defaultdict(empty)
    by_person = []; center_months = []; roles = set(); person_options = []
    quality = dict(center_months=0, closed_months=0, verified_months=0,
                   empty_months=0, unmatched_records=0, current_role_fallback_records=0)
    with core.connect() as c:
        c.execute('BEGIN')
        user = core.fresh_user(c, user)
        centers = core.centers_for(c, user)
        if cid != 'all':
            core.authorize(user, cid)
            if not any(ct['id'] == cid for ct in centers):
                raise ValueError('Centro non disponibile.')
            centers = [ct for ct in centers if ct['id'] == cid]
        can_hr = user['role'] in ('admin', 'manager', 'hr')
        hr_data = hr_summary() if can_hr else None
        can_export = True
        for item in centers:
            center = core.center(c, item['id'])
            if user['role'] not in ('admin', 'manager', 'hr') and not center['config']['operator_export']:
                can_export = False
            people = core.objects(c, 'people', center['id'])
            role_choices = period_roles(c, center['id'], people, first, last)
            roles.update(r for values in role_choices.values() for r in values)
            if can_hr:
                roles.update(p['role'] for p in people)
            if person_id and not any(p['id'] == person_id for p in people):
                raise ValueError('Persona non disponibile nel centro selezionato.')
            matching_role = [p for p in people if not role or role in role_choices[p['id']]]
            if cid != 'all':
                person_options.extend(dict(id=p['id'], name=p['name'], role=p['role']) for p in matching_role)
            selected = {p['id']: p for p in matching_role if not person_id or p['id'] == person_id}
            raw = [json.loads(r[0]) for r in c.execute(
                "SELECT data FROM entries WHERE cid=? AND json_extract(data,'$.day')>=? AND json_extract(data,'$.day')<=?",
                (center['id'], first + '-01', month_days(last)[-1]))]
            known_ids = {p['id'] for p in people}
            quality['unmatched_records'] += sum(e['person_id'] not in known_ids for e in raw)
            entries = [e for e in raw if e['person_id'] in selected]
            effective = entry_people(c, center['id'], entries)
            entries = [e for e in entries if not role or effective[e['person_id'], e['day']]['role'] == role]
            quality['current_role_fallback_records'] += sum(
                effective[e['person_id'], e['day']]['effective_contract'] is None for e in entries)
            actual_keys = {(e['person_id'], e['day'], e['slot']) for e in entries if e['layer'] == 'actual'}
            cb = empty(); per_month = {m: empty() for m in months}
            per_person = defaultdict(empty)
            person_roles = defaultdict(set)
            for entry in entries:
                employee = effective[entry['person_id'], entry['day']]; m = entry['day'][:7]
                person_roles[employee['id']].add(employee['role'])
                for bucket in (total, monthly[m], cb, per_month[m], per_person[employee['id']], by_role[employee['role']]):
                    add(bucket, entry, center, actual_keys)
                if entry['layer'] == 'actual' and entry['kind'] == 'absence':
                    add(by_cause[(entry['code'], entry['code_label'])], entry, center, actual_keys)
            for m in months:
                period = core.period(c, center, m)
                record = dict(cid=center['id'], name=center['name'], code=center['code'], month=m,
                              closed=bool(period['closed']), verified=bool(period['verified']), **finish(per_month[m]))
                center_months.append(record)
                quality['center_months'] += 1
                quality['closed_months'] += record['closed']
                quality['verified_months'] += record['verified']
                quality['empty_months'] += record['actual_records'] == 0
            by_center.append(dict(cid=center['id'], name=center['name'], code=center['code'], **finish(cb)))
            for pid, bucket in per_person.items():
                p = selected[pid]
                by_person.append(dict(cid=center['id'], center=center['name'], id=pid,
                                      name=p['name'], role=' / '.join(sorted(person_roles[pid])),
                                      roles=sorted(person_roles[pid]), **finish(bucket)))
            if can_hr:
                profiles = {r['pid']: json.loads(r['data']) for r in c.execute('SELECT pid,data FROM hr_profiles WHERE cid=?', (center['id'],))}
                documents = defaultdict(list)
                for r in c.execute('SELECT pid,expiry FROM hr_documents WHERE cid=?', (center['id'],)):
                    documents[r['pid']].append(dict(r))
                # HR/onboarding is a present-day view, independent of attendance dates.
                for p in people:
                    if (role and p['role'] != role) or (person_id and p['id'] != person_id):
                        continue
                    include_hr(hr_data, p, profiles.get(p['id']), documents[p['id']], today)
    if hr_data is not None:
        hr_data['as_of'] = today.isoformat()
    return dict(filters=dict(first=first, last=last, cid=cid, role=role, person_id=person_id),
                options=dict(roles=sorted(roles), people=sorted(person_options, key=lambda p: p['name'].casefold())),
                centers=centers, summary=finish(total), monthly=[dict(month=m, **finish(monthly[m])) for m in months],
                by_center=by_center, by_role=[dict(role=k, **finish(v)) for k, v in sorted(by_role.items())],
                by_cause=[dict(code=k[0], label=k[1], **finish(v)) for k, v in sorted(by_cause.items())],
                by_person=sorted(by_person, key=lambda p: (p['center'].casefold(), p['name'].casefold())),
                center_months=center_months, quality=quality, hr=hr_data, export_allowed=can_export,
                role_history_note=ROLE_HISTORY_NOTE, generated_at=core.now(), has_records=bool(by_person))


def export_csv(core, user, first, last, cid='all', role='', person_id=''):
    data = report(core, user, first, last, cid, role, person_id)
    if not data['export_allowed']:
        raise PermissionError('Esportazione non abilitata per tutti i centri selezionati.')
    buf = io.StringIO(); writer = csv.writer(buf, delimiter=';')
    def write(values):
        writer.writerow(["'" + str(x) if str(x).lstrip().startswith(('=', '+', '-', '@')) else x for x in values])
    write(['Centro', 'Codice centro', 'Mese', 'Filtro ruolo', 'Filtro persona (id)', 'Minuti noti',
           'Turni effettivi', 'Turni senza orari', 'Fasce assenza', 'Giornate assenza per anagrafica',
           'Riposi', 'Turni fuori sede', 'Turni festivi', 'Fasce lavoro pianificate',
           'Fasce lavoro senza consuntivo', 'Completezza orari %', 'Quota assenze sulle fasce %',
           'Mese chiuso', 'Calendario verificato', 'Stato dati', 'Storicità ruolo'])
    for row in data['center_months']:
        status = 'SENZA CONSUNTIVI' if not row['actual_records'] else 'PARZIALI: ORARI MANCANTI' if row['missing_hours'] else 'ORARI COMPLETI'
        write([row['name'], row['code'], row['month'], role, person_id,
               row['minutes'] if row['minutes'] is not None else '', row['work_shifts'], row['missing_hours'],
               row['absence_slots'], row['absence_days'], row['rest_slots'], row['external_shifts'], row['festive_shifts'],
               row['planned_work'], row['pending_work'], row['hours_completeness'] if row['hours_completeness'] is not None else '',
               row['absence_share'] if row['absence_share'] is not None else '',
               'SI' if row['closed'] else 'NO', 'SI' if row['verified'] else 'NO', status, ROLE_HISTORY_NOTE])
    return ('\ufeff' + buf.getvalue()).encode('utf-8')
