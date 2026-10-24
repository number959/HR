"""Lista operativa ricavata dai dati autorizzati, senza modificare stati o approvazioni."""
from datetime import date, timedelta
import hr
from rules import duration, month_days


def report(core, user, month, cid='all', today=None):
    days = month_days(month)
    today = today or date.today()
    stamp = today.isoformat()
    horizon = (today + timedelta(days=30)).isoformat()
    with core.connect() as c:
        user = core.fresh_user(c, user)
        centers = core.centers_for(c, user)
        if cid != 'all':
            core.authorize(user, cid)
            core.center(c, cid)
            centers = [v for v in centers if v['id'] == cid]
    can_hr = user['role'] in ('admin', 'manager', 'hr')
    items = []

    def add(category, title, center, pid='', day='', section='', priority='normal', detail=''):
        items.append(dict(id=str(len(items)+1), category=category, title=title,
                          cid=center['id'], center=center['name'], pid=pid,
                          day=day, month=month, section=section, priority=priority, detail=detail))

    for ct in centers:
        snap = core.snapshot(user, ct['id'], month)
        people = {p['id']: p for p in snap['people']}
        entries = snap['entries']
        actual = {(e['person_id'], e['day'], e['slot']) for e in entries if e['layer'] == 'actual'}
        for e in entries:
            person = people.get(e['person_id'])
            if not person:
                continue
            detail = f"{person['name']} · {e['day']} · {e['slot']}"
            if e['layer'] == 'actual' and e['kind'] == 'work' and duration(e) is None:
                add('orari', 'Completa gli orari del turno', ct, person['id'], e['day'],
                    priority='urgent' if snap['period']['closed'] else 'normal', detail=detail)
            elif (e['layer'] == 'planned' and e['kind'] == 'work' and e['day'] <= stamp
                  and (e['person_id'], e['day'], e['slot']) not in actual):
                add('consuntivi', 'Registra il consuntivo', ct, person['id'], e['day'], detail=detail)
        if not snap['period']['verified']:
            add('calendario', 'Verifica calendario e parametri del mese', ct,
                section='controlli', detail=month+' · verifica riservata al responsabile')
        if entries and not snap['period']['closed'] and days[-1] < stamp:
            add('chiusure', 'Controlla il mese ancora aperto', ct, section='riepilogo',
                detail=month+' · chiusura disponibile al responsabile dopo i controlli')
        if can_hr:
            listing = hr.read(core, user, ct['id'])
            for person in listing['employees']:
                if not person['active'] or person['stage'] == 'ended':
                    continue
                if person['version'] == 0:
                    add('fascicoli', 'Compila il fascicolo', ct, person['id'], section='anagrafica', detail=person['name'])
                elif person['total'] > person['done']:
                    add('onboarding', 'Completa le attività di onboarding', ct, person['id'],
                        section='onboarding', priority='urgent' if person['overdue'] else 'normal',
                        detail=f"{person['name']} · {person['total']-person['done']} attività aperte")
            active_ids = {p['id'] for p in listing['employees'] if p['active'] and p['stage'] != 'ended'}
            for deadline in listing['deadlines']:
                if deadline['pid'] in active_ids and deadline['date'] <= horizon:
                    add('scadenze', deadline['label'], ct, deadline['pid'], deadline['date'], deadline['section'],
                        priority='urgent' if deadline['date'] < stamp else 'normal', detail=deadline['name'])
    if user['role'] == 'admin':
        import backup_policy
        backup = backup_policy.status(core, user)
        # The policy exposes a status document; an error is never hidden in the action list.
        error = backup.get('last_error') or backup.get('state', {}).get('last_error')
        if error:
            add('backup', 'Controlla la seconda copia del backup',
                dict(id='', name='Server centrale'), section='esportazioni', priority='urgent', detail=str(error))
    items.sort(key=lambda x: (x['priority'] != 'urgent', x['day'] or '9999', x['center'], x['title']))
    counts = {category: sum(x['category'] == category for x in items) for category in sorted({x['category'] for x in items})}
    return dict(items=items, counts=counts, total=len(items), urgent=sum(x['priority']=='urgent' for x in items),
                centers=centers, month=month, as_of=stamp, generated_at=core.now(), hr_visible=can_hr)
