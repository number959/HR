"""Approvazione mensile: struttura → responsabile → HR centrale.

Il percorso è disattivato per impostazione predefinita e si attiva per struttura.
Ogni passaggio confronta versione e impronta dei dati nella stessa transazione:
dopo l'invio il mese è bloccato finché non viene restituito o riaperto.
L'approvazione finale di HR chiude il mese senza dare a HR il permesso di
modificare le presenze. Questo modulo non invia email.
"""
import hashlib
import json

from . import audit, centers, months, users
from .errors import Conflict, Forbidden, Invalid
from .permissions import has, require
from .util import month_days, stamp
from . import validate as v

LABELS = {'draft': 'In compilazione', 'submitted': 'Da verificare dal responsabile',
          'manager_approved': 'In attesa di HR', 'hr_approved': 'Approvato da HR',
          'returned': 'Restituito per correzioni'}
FROZEN = {'submitted', 'manager_approved', 'hr_approved'}
ACTION_LABELS = {'submit': 'Invia al responsabile', 'manager_approve': 'Verifica e inoltra a HR',
                 'hr_approve': 'Approva e chiudi', 'return': 'Restituisci per correzioni', 'reopen': 'Riapri il mese'}
TARGET = {'submit': 'submitted', 'manager_approve': 'manager_approved', 'hr_approve': 'hr_approved',
          'return': 'returned', 'reopen': 'returned'}


def policy(con, center_id):
    found = con.execute('SELECT * FROM approval_policies WHERE center_id=?', (center_id,)).fetchone()
    if not found:
        return dict(enabled=False, reason='', version=0, updated_at='', updated_by='')
    return dict(enabled=bool(found['enabled']), reason=found['reason'], version=found['version'],
                updated_at=found['updated_at'], updated_by=found['updated_by'])


def workflow(con, center_id, month):
    found = con.execute('SELECT * FROM approvals WHERE center_id=? AND month=?', (center_id, month)).fetchone()
    out = (dict(status=found['status'], fingerprint=found['fingerprint'], note=found['note'], version=found['version'],
                updated_at=found['updated_at'], updated_by=found['updated_by']) if found else
           dict(status='draft', fingerprint='', note='', version=0, updated_at='', updated_by=''))
    out['label'] = LABELS[out['status']]
    return out


def fingerprint(con, center_id, month):
    """Impronta dei dati che l'approvazione certifica. Una modifica in un altro mese non la cambia."""
    center = centers.row(con, center_id)
    state = months.get(con, center_id, month)
    cfg, _ = months.configuration(con, center_id, state)
    days = month_days(month)
    people = months.people(con, center_id)
    ids = [p['id'] for p in people]
    marks = ','.join('?' * len(ids)) or "''"

    def rows(sql, args=()):
        return [dict(r) for r in con.execute(sql, args)]

    data = dict(
        center=dict(id=center['id'], name=center['name'], code=center['code']),
        month=dict(rules_version=state['rules_version'], verified=state['verified']), config=cfg,
        people=[{k: p[k] for k in ('id', 'identity_id', 'name', 'role', 'registration', 'active', 'contract', 'pay_override')}
                for p in people],
        entries=[{k: e[k] for k in months.ENTRY_FIELDS if k not in ('updated_at', 'updated_by')}
                 for e in sorted(months.entries(con, center_id, month), key=lambda e: e['id'])],
        workload=rows('SELECT day,slot,ordinary,isolated FROM workload WHERE center_id=? AND day LIKE ? ORDER BY day,slot',
                      (center_id, month + '-%')),
        agreements=rows('SELECT person_id,data,version FROM agreements WHERE center_id=? AND month=? ORDER BY person_id',
                        (center_id, month)),
        contracts=rows(f'''SELECT id,person_id,valid_from,valid_to,data,version FROM contracts WHERE person_id IN ({marks})
                           AND valid_from<=? AND (valid_to='' OR valid_to>=?) ORDER BY id''', (*ids, days[-1], days[0])),
        economics=rows(f'''SELECT id,person_id,valid_from,valid_to,data,version FROM economics WHERE person_id IN ({marks})
                           AND valid_from<=? AND (valid_to='' OR valid_to>=?) ORDER BY id''', (*ids, days[-1], days[0])))
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(text.encode()).hexdigest()


def available_actions(user, pol, wf, closed, stale):
    if not pol['enabled']:
        return []
    if closed:
        return ['reopen'] if has(user, 'approvazioni.riapri') else []
    state = wf['status']
    if state in ('draft', 'returned'):
        return ['submit'] if has(user, 'approvazioni.invia') else []
    if state == 'submitted' and has(user, 'approvazioni.verifica'):
        return ([] if stale else ['manager_approve']) + ['return']
    if state == 'manager_approved' and has(user, 'approvazioni.approva'):
        return ([] if stale else ['hr_approve']) + ['return']
    if state == 'submitted' and has(user, 'approvazioni.approva'):
        return ['return']
    return []


def _status(con, user, center_id, month):
    pol = policy(con, center_id)
    wf = workflow(con, center_id, month)
    state = months.get(con, center_id, month)
    current = fingerprint(con, center_id, month)
    stale = bool(wf['fingerprint'] and wf['status'] in FROZEN and wf['fingerprint'] != current)
    return pol, wf, state, current, stale


def metadata(con, user, center_id, month):
    """Riassunto per la pagina presenze (connessione già autorizzata dal chiamante)."""
    pol, wf, state, _, stale = _status(con, user, center_id, month)
    return dict(enabled=pol['enabled'], status=wf['status'], label=wf['label'], version=wf['version'],
                frozen=bool(pol['enabled'] and wf['status'] in FROZEN), stale=stale,
                legacy_closed=bool(state['closed'] and wf['status'] != 'hr_approved'))


def read(db, user, center_id, month):
    v.month(month)
    with db.read() as con:
        user, center = centers.scoped(con, user, center_id, 'approvazioni.vedi')
        pol, wf, state, current, stale = _status(con, user, center_id, month)
        rows = months.entries(con, center_id, month)
        history = [dict(r) for r in con.execute(
            'SELECT version,action,status,note,at,actor FROM approval_history WHERE center_id=? AND month=? '
            'ORDER BY version DESC LIMIT 200', (center_id, month))]
        for h in history:
            h['label'] = ACTION_LABELS.get(h['action'], h['action'])
        acts = available_actions(user, pol, wf, state['closed'], stale)
        return dict(center=dict(id=center['id'], name=center['name']), month=month, workflow=wf, policy=pol,
                    fingerprint=current, stale=stale, verified=state['verified'], closed=state['closed'],
                    legacy_closed=bool(state['closed'] and wf['status'] != 'hr_approved'),
                    can_configure=has(user, 'approvazioni.configura'),
                    actions=[dict(id=a, label=ACTION_LABELS[a]) for a in acts],
                    checks=months.close_checks(con, center_id, month), history=history,
                    summary=dict(people=con.execute('SELECT count(*) FROM people WHERE center_id=?', (center_id,)).fetchone()[0],
                                 entries=len(rows),
                                 work_entries=sum(e['kind'] == 'work' and e['layer'] == 'actual' for e in rows)))


def queue(db, user, month):
    """Stato del mese in tutte le strutture visibili: cosa attende il mio intervento."""
    v.month(month)
    with db.read() as con:
        user = users.reload(con, user)
        require(user, 'approvazioni.vedi')
        out = []
        for c in centers.visible(con, user):
            if not c['active']:
                continue
            pol, wf, state, _, stale = _status(con, user, c['id'], month)
            acts = available_actions(user, pol, wf, state['closed'], stale)
            out.append(dict(center_id=c['id'], center=c['name'], enabled=pol['enabled'], status=wf['status'],
                            label=wf['label'] if pol['enabled'] else ('Chiuso' if state['closed'] else 'Percorso non attivo'),
                            closed=state['closed'], stale=stale, actions=acts, mine=bool(acts and acts != ['reopen'])))
        return dict(month=month, centers=out, waiting=sum(r['mine'] for r in out))


def configure(db, actor, center_id, raw):
    v.keys(raw, {'enabled', 'reason', 'version'}, 'Percorso di approvazione', required={'enabled', 'reason', 'version'})
    enabled = v.boolean(raw['enabled'], 'Approvazione attiva', field='enabled')
    reason = v.reason(raw['reason'])
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'approvazioni.configura')
        old = policy(con, center_id)
        if v.version(raw['version']) != old['version']:
            raise Conflict('Configurazione cambiata in un’altra sessione: ricaricare.')
        if not enabled and con.execute("SELECT 1 FROM approvals WHERE center_id=? AND status IN ('submitted','manager_approved')",
                                       (center_id,)).fetchone():
            raise Invalid('Restituire o completare prima i mesi con approvazione in corso.')
        con.execute('''INSERT INTO approval_policies(center_id,enabled,reason,version,updated_at,updated_by) VALUES(?,?,?,?,?,?)
                       ON CONFLICT(center_id) DO UPDATE SET enabled=excluded.enabled, reason=excluded.reason,
                       version=excluded.version, updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (center_id, int(enabled), reason, old['version'] + 1, stamp(), actor.username))
        new = policy(con, center_id)
        audit.record(con, actor, 'Percorso di approvazione ' + ('attivato' if enabled else 'disattivato'), center_id,
                     entity='approval_policy', entity_id=center_id, before=old, after=new)
    return dict(policy=new)


def _save(con, actor, center_id, month, wf, status, action, note, print_):
    version = wf['version'] + 1
    con.execute('''INSERT INTO approvals(center_id,month,status,fingerprint,note,version,updated_at,updated_by)
                   VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(center_id,month) DO UPDATE SET status=excluded.status,
                   fingerprint=excluded.fingerprint, note=excluded.note, version=excluded.version,
                   updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                (center_id, month, status, print_, note, version, stamp(), actor.username))
    con.execute('INSERT INTO approval_history(center_id,month,version,action,status,note,fingerprint,at,actor) '
                'VALUES(?,?,?,?,?,?,?,?,?)', (center_id, month, version, action, status, note, print_, stamp(), actor.username))
    audit.record(con, actor, 'Approvazione del mese: ' + ACTION_LABELS[action].lower(), center_id, entity='approval',
                 entity_id=month, before=dict(status=wf['status'], version=wf['version']),
                 after=dict(status=status, version=version, note=note))


def transition(db, actor, center_id, month, raw):
    v.month(month)
    v.keys(raw, {'action', 'version', 'fingerprint', 'note', 'calendar_checked'}, 'Passaggio',
           required={'action', 'version', 'fingerprint'})
    action = v.choice(raw['action'], 'Passaggio', TARGET, field='action')
    note = (v.reason(raw.get('note'), 'Motivazione', field='note') if action in ('return', 'reopen')
            else v.text(raw.get('note', ''), 'Nota', 2000, multiline=True, field='note'))
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'approvazioni.vedi')
        pol, wf, state, current, stale = _status(con, actor, center_id, month)
        if v.version(raw['version']) != wf['version'] or raw['fingerprint'] != current:
            raise Conflict('Dati o stato del mese cambiati: ricaricare prima di procedere.')
        if action not in available_actions(actor, pol, wf, state['closed'], stale):
            raise Forbidden('Passaggio non consentito per il profilo o lo stato attuale. '
                            'Se i dati sono cambiati, restituire prima il mese.')
        if action == 'manager_approve' and not state['verified']:
            if raw.get('calendar_checked') is not True:
                raise Invalid('Confermare di aver verificato calendario e parametri del mese.', field='calendar_checked')
            state = months.update(con, center_id, month, actor, verified=True)
        if action in ('submit', 'manager_approve', 'hr_approve'):
            problems = months.close_checks(con, center_id, month, include_calendar=action != 'submit')
            if problems:
                raise Invalid(' '.join(problems))
        if action == 'hr_approve':
            months.update(con, center_id, month, actor, closed=True)
        elif action in ('return', 'reopen'):
            months.update(con, center_id, month, actor, closed=False, verified=False, note=note)
        _save(con, actor, center_id, month, wf, TARGET[action], action, note, fingerprint(con, center_id, month))
    return read(db, actor, center_id, month)


# --- vincoli usati dagli altri moduli (nella transazione del chiamante) -----------------------

def guard_reference_change(con, center_id):
    """Parametri e anagrafiche non cambiano mentre un mese è in approvazione."""
    if policy(con, center_id)['enabled'] and con.execute(
            "SELECT 1 FROM approvals WHERE center_id=? AND status IN ('submitted','manager_approved')", (center_id,)).fetchone():
        raise Invalid('Prima di modificare dati di riferimento, restituire i mesi con approvazione in corso.')


def guard_month(con, actor, center_id, month, action='edit', reason=''):
    """action: 'edit' (presenze, accordi, carico), 'close' o 'reopen'."""
    pol = policy(con, center_id)
    wf = workflow(con, center_id, month)
    if pol['enabled']:
        if action in ('close', 'reopen'):
            raise Invalid('Per questa struttura chiusura e riapertura passano dalla pagina Approvazioni.')
        if wf['status'] in FROZEN:
            raise Invalid('Mese inviato o approvato: chiedere la restituzione o la riapertura dalla pagina Approvazioni.')
    elif action == 'reopen' and wf['status'] in FROZEN:
        # Riapertura con il percorso disattivato: l'approvazione HR precedente non vale più.
        _save(con, actor, center_id, month, wf, 'returned', 'reopen', reason, '')


def require_approved(con, center_id, month):
    """Per le esportazioni paghe: con il percorso attivo serve l'approvazione HR ancora valida."""
    if not policy(con, center_id)['enabled']:
        return
    wf = workflow(con, center_id, month)
    state = months.get(con, center_id, month)
    if state['closed'] and wf['version'] == 0:
        return  # chiusura precedente all'attivazione del percorso: resta una chiusura storica
    if wf['status'] != 'hr_approved' or not state['closed']:
        raise Invalid('Il mese richiede l’approvazione finale di HR prima dell’esportazione paghe.')
    if wf['fingerprint'] != fingerprint(con, center_id, month):
        raise Invalid('Dati cambiati dopo l’approvazione HR: riaprire e verificare di nuovo il mese.')


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/approvals/<month>', cap='approvazioni.vedi')
def api_queue(ctx):
    return queue(ctx.db, ctx.user, ctx.params['month'])


@route('GET', '/api/approvals/<cid>/<month>', cap='approvazioni.vedi')
def api_read(ctx):
    return read(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'])


@route('POST', '/api/approvals/<cid>/<month>', cap='approvazioni.vedi')
def api_transition(ctx):
    return transition(ctx.db, ctx.user, ctx.params['cid'], ctx.params['month'], ctx.body)


@route('PUT', '/api/approvals/<cid>/policy', cap='approvazioni.configura', step_up=True)
def api_configure(ctx):
    return configure(ctx.db, ctx.user, ctx.params['cid'], ctx.body)
