"""Registro delle attività: chi ha fatto cosa, quando, con i valori prima e dopo."""
from .util import dumps, loads, stamp


def record(con, actor, action, center_id=None, *, entity='', entity_id='', before=None, after=None):
    username = getattr(actor, 'username', None) or (actor.get('username') if isinstance(actor, dict) else str(actor))
    con.execute('INSERT INTO audit(at,actor,center_id,action,entity,entity_id,before,after) VALUES(?,?,?,?,?,?,?,?)',
                (stamp(), username, center_id, action, entity, entity_id or '',
                 None if before is None else dumps(before), None if after is None else dumps(after)))


def recent(con, center_id, limit=60):
    return [dict(at=r['at'], actor=r['actor'], action=r['action'], entity=r['entity'])
            for r in con.execute('SELECT at,actor,action,entity FROM audit WHERE center_id=? ORDER BY id DESC LIMIT ?',
                                 (center_id, limit))]


def details(con, center_id, limit=200):
    return [dict(id=r['id'], at=r['at'], actor=r['actor'], action=r['action'], entity=r['entity'],
                 entity_id=r['entity_id'], before=loads(r['before']), after=loads(r['after']))
            for r in con.execute('SELECT * FROM audit WHERE center_id=? ORDER BY id DESC LIMIT ?', (center_id, limit))]
