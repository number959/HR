"""Approvazione mensile sede → responsabile → HR, disattivata per le sedi esistenti.

Ogni passaggio confronta versione e impronta dei dati nella stessa transazione.
L'approvazione finale chiude il periodo senza attribuire a HR il permesso di
modificare le presenze. Nessuna email viene inviata da questo modulo.
"""
import hashlib
import json
from rules import month_days, totals, duration

LABELS = {'draft': 'In compilazione', 'submitted': 'Da verificare dal responsabile',
          'manager_approved': 'In attesa di HR', 'hr_approved': 'Approvato da HR',
          'returned': 'Restituito per correzioni'}
FROZEN = {'submitted', 'manager_approved', 'hr_approved'}


def init(app):
    with app.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS approval_policies(
            cid TEXT PRIMARY KEY REFERENCES centers(id),version INTEGER NOT NULL,
            enabled INTEGER NOT NULL,reason TEXT NOT NULL,updated_at TEXT NOT NULL,updated_by TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS approval_months(
            cid TEXT NOT NULL REFERENCES centers(id),month TEXT NOT NULL,version INTEGER NOT NULL,
            status TEXT NOT NULL,fingerprint TEXT NOT NULL,note TEXT NOT NULL,
            updated_at TEXT NOT NULL,updated_by TEXT NOT NULL,PRIMARY KEY(cid,month));
        CREATE TABLE IF NOT EXISTS approval_history(
            cid TEXT NOT NULL,month TEXT NOT NULL,version INTEGER NOT NULL,
            action TEXT NOT NULL,status TEXT NOT NULL,note TEXT NOT NULL,
            fingerprint TEXT NOT NULL,stamp TEXT NOT NULL,actor TEXT NOT NULL,
            PRIMARY KEY(cid,month,version),FOREIGN KEY(cid,month) REFERENCES approval_months(cid,month));
        ''')
        c.commit()


def _scope(app, c, user, cid, month=None):
    if not isinstance(cid, str) or not cid:
        raise ValueError('Indicare una struttura valida.')
    user = app.fresh_user(c, user)
    app.authorize(user, cid)
    ct = app.center(c, cid)
    if month is not None:
        if not isinstance(month, str):
            raise ValueError('Indicare un mese valido.')
        month_days(month)
    return user, ct


def _version(value):
    if type(value) is not int or value < 0:
        raise ValueError('Versione non valida. Ricaricare i dati.')
    return value


def _note(value, required=False):
    if not isinstance(value, str) or len(value) > 2000 or any(ord(x) < 32 and x not in '\n\t' for x in value):
        raise ValueError('Nota non valida: massimo 2000 caratteri.')
    value = value.strip()
    if required and len(value) < 8:
        raise ValueError('Indicare una motivazione di almeno 8 caratteri.')
    return value


def _policy(c, cid):
    row = c.execute('SELECT * FROM approval_policies WHERE cid=?', (cid,)).fetchone()
    return {**dict(row), 'enabled': bool(row['enabled'])} if row else dict(cid=cid, version=0, enabled=False,
                                                                        reason='', updated_at='', updated_by='')


def _workflow(c, cid, month):
    row = c.execute('SELECT * FROM approval_months WHERE cid=? AND month=?', (cid, month)).fetchone()
    wf = dict(row) if row else dict(cid=cid, month=month, version=0, status='draft', fingerprint='',
                                    note='', updated_at='', updated_by='')
    wf['label'] = LABELS[wf['status']]
    return wf


def _fingerprint(app, c, ct, month):
    p = app.period(c, ct, month)
    # A later edit in a different month does not invalidate this month. Changes
    # to anagraphic/contract data used by exports do require a new verification.
    data = dict(center={k: ct[k] for k in ('id', 'name', 'code', 'config')},
                period={k: p.get(k) for k in ('config', 'version', 'verified', 'agreements')},
                people=sorted(app.objects(c, 'people', ct['id']), key=lambda x: x['id']),
                entries=sorted([e for e in app.objects(c, 'entries', ct['id']) if e['day'].startswith(month+'-')], key=lambda x: x['id']),
                patients=sorted([e for e in app.objects(c, 'patients', ct['id']) if e['day'].startswith(month+'-')], key=lambda x: x['id']))
    last = month_days(month)[-1]
    for table in ('workforce_contracts', 'workforce_economics'):
        data[table] = [dict(row) for row in c.execute(
            'SELECT * FROM '+table+" WHERE cid=? AND effective_from<=? AND (effective_to='' OR effective_to>=?) ORDER BY id",
            (ct['id'], last, month+'-01'))]
    data['assignments'] = [dict(row) for row in c.execute('SELECT * FROM workforce_assignments WHERE cid=? ORDER BY pid', (ct['id'],))]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _checks(app, c, ct, month, include_calendar=True):
    p = app.period(c, ct, month); cfg = app.effective_rules(ct, p)
    entries = app.objects(c, 'entries', ct['id']); people = app.objects(c, 'people', ct['id'])
    selected = [e for e in entries if e['day'].startswith(month+'-') and e['layer'] == 'actual']
    checks = []
    if include_calendar and not p['verified']:
        checks.append('Verificare calendario e parametri prima dell’approvazione finale.')
    if not selected:
        checks.append('Mese senza registrazioni effettive.')
    if any(r['pending'] for r in totals(people, entries, month)):
        checks.append('Completare le fasce pianificate rimaste senza consuntivo.')
    if any('da specificare' in e['work_site'] or 'Colore sede da verificare' in e['note'] for e in selected):
        checks.append('Risolvere le sedi importate non definite.')
    if cfg['require_times_on_close'] and any(e['kind'] == 'work' and duration(e) is None for e in selected):
        checks.append('Completare gli orari richiesti per la chiusura.')
    return checks


def _actions(user, policy, wf, closed, legacy, stale):
    if not policy['enabled']:
        return []
    role = user['role']; state = wf['status']
    if closed:
        return ['reopen'] if role in ('admin', 'hr', 'manager') else []
    if state in ('draft', 'returned'):
        return ['submit'] if role in ('admin', 'manager', 'operator') else []
    if state == 'submitted' and role in ('admin', 'manager'):
        return (['manager_approve'] if not stale else []) + ['return']
    if state == 'manager_approved' and role in ('admin', 'hr'):
        return (['hr_approve'] if not stale else []) + ['return']
    if state == 'submitted' and role == 'hr':
        return ['return']
    return []


def metadata(app, c, user, ct, month):
    """Small snapshot field; caller already holds the scoped read connection."""
    policy = _policy(c, ct['id']); wf = _workflow(c, ct['id'], month)
    p = app.period(c, ct, month)
    stale = bool(wf['fingerprint'] and wf['status'] in FROZEN and wf['fingerprint'] != _fingerprint(app, c, ct, month))
    return dict(enabled=policy['enabled'], status=wf['status'], label=wf['label'], version=wf['version'],
                frozen=bool(policy['enabled'] and wf['status'] in FROZEN), stale=stale,
                legacy_closed=bool(p['closed'] and wf['status'] != 'hr_approved'))


def read(app, user, cid, month):
    with app.connect() as c:
        user, ct = _scope(app, c, user, cid, month)
        p = app.period(c, ct, month); policy = _policy(c, cid); wf = _workflow(c, cid, month)
        fingerprint = _fingerprint(app, c, ct, month)
        stale = bool(wf['fingerprint'] and wf['status'] in FROZEN and wf['fingerprint'] != fingerprint)
        legacy = bool(p['closed'] and wf['status'] != 'hr_approved')
        entries = [e for e in app.objects(c, 'entries', cid) if e['day'].startswith(month+'-')]
        history = [dict(row) for row in c.execute('SELECT * FROM approval_history WHERE cid=? AND month=? ORDER BY version DESC LIMIT 200', (cid, month))]
        return dict(cid=cid, month=month, workflow=wf, policy=policy, fingerprint=fingerprint, stale=stale,
                    legacy_closed=legacy, verified=p['verified'], closed=p['closed'],
                    can_configure=user['role'] == 'admin',
                    actions=_actions(user, policy, wf, p['closed'], legacy, stale),
                    checks=_checks(app, c, ct, month), history=history,
                    summary=dict(people=len(app.objects(c, 'people', cid)), entries=len(entries),
                                 work_entries=sum(e['kind'] == 'work' and e['layer'] == 'actual' for e in entries)))


def configure(app, user, body):
    cid = body.get('cid'); version = _version(body.get('version')); reason = _note(body.get('reason', ''), True)
    enabled = body.get('enabled')
    if type(enabled) is not bool:
        raise ValueError('L’attivazione deve essere Sì o No.')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE'); user, ct = _scope(app, c, user, cid); app.require_admin(user)
        old = _policy(c, cid)
        if old['version'] != version:
            raise ValueError('Configurazione cambiata. Ricaricare prima di salvare.')
        if not enabled and c.execute("SELECT 1 FROM approval_months WHERE cid=? AND status IN ('submitted','manager_approved')", (cid,)).fetchone():
            raise ValueError('Restituire o completare prima tutti i mesi con approvazione in corso.')
        stamp = app.now()
        c.execute('INSERT INTO approval_policies VALUES(?,?,?,?,?,?) ON CONFLICT(cid) DO UPDATE SET version=excluded.version,enabled=excluded.enabled,reason=excluded.reason,updated_at=excluded.updated_at,updated_by=excluded.updated_by',
                  (cid, version+1, int(enabled), reason, stamp, user['username']))
        new = _policy(c, cid); app.audit(c, user, 'Configurazione approvazione mensile', cid, old, new); c.commit()
    return {'ok': True, 'policy': new}


def _save(app, c, user, cid, month, wf, status, action, note, fingerprint):
    stamp = app.now(); version = wf['version']+1
    c.execute('INSERT INTO approval_months VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(cid,month) DO UPDATE SET version=excluded.version,status=excluded.status,fingerprint=excluded.fingerprint,note=excluded.note,updated_at=excluded.updated_at,updated_by=excluded.updated_by',
              (cid, month, version, status, fingerprint, note, stamp, user['username']))
    c.execute('INSERT INTO approval_history VALUES(?,?,?,?,?,?,?,?,?)',
              (cid, month, version, action, status, note, fingerprint, stamp, user['username']))
    app.audit(c, user, 'Approvazione mese: '+action, cid, wf, _workflow(c, cid, month))


def transition(app, user, body):
    cid = body.get('cid'); month = body.get('month'); version = _version(body.get('version'))
    action = body.get('action')
    if not isinstance(action, str) or action not in ('submit', 'manager_approve', 'hr_approve', 'return', 'reopen'):
        raise ValueError('Passaggio non valido.')
    note = _note(body.get('note', ''), action in ('return', 'reopen'))
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE'); user, ct = _scope(app, c, user, cid, month)
        policy = _policy(c, cid); wf = _workflow(c, cid, month); p = app.period(c, ct, month)
        fingerprint = _fingerprint(app, c, ct, month)
        if version != wf['version'] or not isinstance(body.get('fingerprint'), str) or body['fingerprint'] != fingerprint:
            raise ValueError('I dati o lo stato sono cambiati. Ricaricare prima di procedere.')
        stale = bool(wf['fingerprint'] and wf['status'] in FROZEN and wf['fingerprint'] != fingerprint)
        if action not in _actions(user, policy, wf, p['closed'], bool(p['closed'] and wf['status'] != 'hr_approved'), stale):
            raise PermissionError('Passaggio non consentito per il ruolo o lo stato attuale. Se i dati sono cambiati, restituire prima il mese.')
        if action in ('submit', 'manager_approve', 'hr_approve'):
            if action == 'manager_approve' and not p['verified']:
                if body.get('calendar_checked') is not True:
                    raise ValueError('Confermare la verifica di calendario e parametri.')
                p['verified'] = True
                app.put_period(c, cid, month, p)
            checks = _checks(app, c, ct, month, include_calendar=action != 'submit')
            if checks:
                raise ValueError(' '.join(checks))
        if action == 'hr_approve':
            p['closed'] = True
            app.put_period(c, cid, month, p)
        elif action in ('return', 'reopen'):
            p['closed'] = False; p['verified'] = False; p['note'] = note
            app.put_period(c, cid, month, p)
        status = {'submit': 'submitted', 'manager_approve': 'manager_approved', 'hr_approve': 'hr_approved',
                  'return': 'returned', 'reopen': 'returned'}[action]
        fingerprint = _fingerprint(app, c, ct, month)
        _save(app, c, user, cid, month, wf, status, action, note, fingerprint)
        c.execute('UPDATE centers SET revision=revision+1 WHERE id=?', (cid,)); c.commit()
    return read(app, user, cid, month)


def guard_mutation(app, c, user, action, body):
    """Use the caller's transaction. No commit and no nested connection."""
    cid = body.get('cid')
    if not cid:
        return
    policy = _policy(c, cid)
    if action in ('center_save', 'person') and policy['enabled']:
        if c.execute("SELECT 1 FROM approval_months WHERE cid=? AND status IN ('submitted','manager_approved')", (cid,)).fetchone():
            raise ValueError('Prima di modificare dati di riferimento, restituire i mesi con approvazione in corso.')
    month = body.get('month')
    if not month:
        return
    wf = _workflow(c, cid, month)
    if policy['enabled']:
        if action in ('close', 'reopen'):
            raise ValueError('Usare la pagina Approvazioni per chiudere o riaprire questo mese.')
        if wf['status'] in FROZEN:
            raise ValueError('Mese inviato o approvato: richiedere la restituzione o la riapertura dalla pagina Approvazioni.')
    elif action == 'reopen' and wf['status'] in FROZEN:
        # An authorized legacy reopen must invalidate the previous HR approval,
        # even when the organization has since disabled the workflow.
        note = _note(body.get('reason', ''), True)
        _save(app, c, user, cid, month, wf, 'returned', 'reopen', note, '')


def require_approved(app, c, user, cid, month):
    user, ct = _scope(app, c, user, cid, month)
    if not _policy(c, cid)['enabled']:
        return
    wf = _workflow(c, cid, month); p = app.period(c, ct, month)
    if p['closed'] and wf['version'] == 0:
        return  # Historical closures retain their historical status, never HR approval.
    if wf['status'] != 'hr_approved' or not p['closed']:
        raise ValueError('Il mese richiede l’approvazione finale di HR prima dell’esportazione paghe.')
    if wf['fingerprint'] != _fingerprint(app, c, ct, month):
        raise ValueError('Dati cambiati dopo l’approvazione HR: riaprire e verificare nuovamente il mese.')
