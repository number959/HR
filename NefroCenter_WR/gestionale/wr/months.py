"""Stato del mese di una struttura e dati del registro usati da più moduli.

Un mese senza riga in archivio usa i parametri correnti; la riga viene creata
alla prima scrittura e da quel momento conserva la versione dei parametri.
"""
from datetime import date

from . import centers, rules
from .errors import Conflict, Invalid
from .util import loads, month_days, stamp
from . import validate as v

ENTRY_FIELDS = ('id', 'person_id', 'day', 'slot', 'layer', 'code', 'kind', 'label', 'start', 'end', 'pause',
                'overnight', 'site', 'holiday', 'credit', 'note', 'source', 'review', 'rules_version', 'version',
                'updated_at', 'updated_by')


def get(con, center_id, month):
    v.month(month)
    found = con.execute('SELECT * FROM months WHERE center_id=? AND month=?', (center_id, month)).fetchone()
    if found:
        out = dict(found)
        out.update(verified=bool(out['verified']), closed=bool(out['closed']), stored=True)
        return out
    return dict(center_id=center_id, month=month, rules_version=centers.row(con, center_id)['config_version'],
                verified=False, closed=False, note='', version=0, updated_at='', updated_by='', stored=False)


def ensure(con, center_id, month, actor):
    state = get(con, center_id, month)
    if not state['stored']:
        con.execute('INSERT INTO months(center_id,month,rules_version,verified,closed,note,version,updated_at,updated_by) '
                    'VALUES(?,?,?,0,0,?,1,?,?)', (center_id, month, state['rules_version'], '', stamp(), actor.username))
        state = get(con, center_id, month)
    return state


def update(con, center_id, month, actor, **changes):
    state = ensure(con, center_id, month, actor)
    allowed = {'verified', 'closed', 'note', 'rules_version'}
    if set(changes) - allowed:
        raise ValueError('Campo del mese non previsto.')
    fields = ', '.join(f'{k}=?' for k in changes)
    values = [int(x) if isinstance(x, bool) else x for x in changes.values()]
    con.execute(f'UPDATE months SET {fields}, version=version+1, updated_at=?, updated_by=? WHERE center_id=? AND month=?',
                (*values, stamp(), actor.username, center_id, month))
    return get(con, center_id, month)


def check_version(state, sent):
    if v.version(sent) != state['version']:
        raise Conflict('Lo stato del mese è cambiato in un’altra sessione: ricaricare.')


def configuration(con, center_id, state):
    """Parametri del mese con i permessi del compilatore sempre aggiornati."""
    month_config = centers.config(con, center_id, state['rules_version'])
    current = centers.config(con, center_id)
    return rules.effective(month_config, current), current


def entry_dict(r):
    out = {k: r[k] for k in ENTRY_FIELDS}
    out['overnight'] = bool(out['overnight'])
    out['holiday'] = bool(out['holiday'])
    return out


def entries(con, center_id, month):
    return [entry_dict(r) for r in con.execute(
        'SELECT * FROM entries WHERE center_id=? AND day LIKE ? ORDER BY day, slot', (center_id, month + '-%'))]


def people(con, center_id):
    return [person_dict(r) for r in con.execute(
        'SELECT * FROM people WHERE center_id=? ORDER BY name COLLATE NOCASE', (center_id,))]


def person_dict(r):
    return dict(id=r['id'], center_id=r['center_id'], identity_id=r['identity_id'], name=r['name'], role=r['role'],
                registration=r['registration'], active=bool(r['active']), note=r['note'], contract=r['contract'],
                pay_override=loads(r['pay_override']) if r['pay_override'] else None, version=r['version'])


def close_checks(con, center_id, month, *, include_calendar=True):
    """Controlli comuni a chiusura del mese e approvazione: elenco vuoto se tutto è in ordine."""
    state = get(con, center_id, month)
    cfg, _ = configuration(con, center_id, state)
    rows = entries(con, center_id, month)
    actual = [e for e in rows if e['layer'] == 'actual']
    checks = []
    if include_calendar and not state['verified']:
        checks.append('Verificare calendario e parametri del mese.')
    if not actual:
        checks.append('Mese senza registrazioni effettive.')
    keys = {(e['person_id'], e['day'], e['slot']) for e in actual}
    if any((e['person_id'], e['day'], e['slot']) not in keys for e in rows if e['layer'] == 'planned'):
        checks.append('Completare le fasce pianificate rimaste senza consuntivo.')
    if any(e['review'] for e in actual):
        checks.append('Risolvere le registrazioni importate da verificare (per esempio sedi non riconosciute).')
    if cfg['require_times_on_close'] and any(e['kind'] == 'work' and rules.duration(e) is None for e in actual):
        checks.append('Completare gli orari dei turni: i parametri li richiedono per la chiusura.')
    return checks


def days_info(month, cfg):
    names = ['lun', 'mar', 'mer', 'gio', 'ven', 'sab', 'dom']
    out = []
    for d in month_days(month):
        wd = date.fromisoformat(d).weekday()
        out.append(dict(day=d, weekday=wd, short=names[wd], holiday=d in cfg['holidays'],
                        working=wd in cfg['weekdays'] and d not in cfg['holidays']))
    return out


def require_open(state):
    if state['closed']:
        raise Invalid('Mese chiuso: per modificarlo serve la riapertura motivata.')
