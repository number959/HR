"""Verifica dei documenti da parte di HR centrale.

Esiti: ricevuto (da verificare), da correggere, verificato. La struttura può
ripresentare un documento da correggere. La scadenza resta un avviso calcolato
dalla data: non cambia mai una decisione registrata. Lo storico è completo.
"""
from . import audit, centers
from .errors import Conflict, Forbidden, Invalid, NotFound
from .permissions import has
from .util import stamp, today
from . import validate as v

STATUSES = {'received': 'Ricevuto · da verificare', 'needs_correction': 'Da correggere', 'verified': 'Verificato da HR'}
MAX_PAGE = 100


def current(con, doc, on=None):
    """Stato corrente della verifica (connessione già autorizzata dal chiamante)."""
    found = con.execute('SELECT * FROM document_reviews WHERE document_id=?', (doc['id'],)).fetchone()
    on = on or today().isoformat()
    out = (dict(status=found['status'], note=found['note'], version=found['version'], updated_at=found['updated_at'],
                updated_by=found['updated_by']) if found else
           dict(status='received', note='', version=0, updated_at=doc.get('uploaded_at', ''), updated_by=doc.get('uploaded_by', '')))
    out['label'] = STATUSES[out['status']]
    out['expired'] = bool(doc.get('expiry') and doc['expiry'] < on)
    out['effective'] = 'expired' if out['expired'] else out['status']
    return out


def registered(con, actor, doc_id):
    """Nuovo allegato: stato «ricevuto», nella transazione del caricamento."""
    con.execute("INSERT INTO document_reviews(document_id,status,note,version,updated_at,updated_by) VALUES(?,'received','',1,?,?)",
                (doc_id, stamp(), actor.username))
    con.execute("INSERT INTO document_review_history(document_id,version,status,note,at,actor) VALUES(?,1,'received','',?,?)",
                (doc_id, stamp(), actor.username))


def _document(con, center_id, doc_id):
    found = con.execute('''SELECT id,center_id,person_id,name,category,expiry,mime,size,sha256,uploaded_at,uploaded_by
                           FROM documents WHERE id=? AND center_id=?''', (v.identifier(doc_id, 'Documento'), center_id)).fetchone()
    if not found:
        raise NotFound('Documento non trovato nella struttura.')
    return dict(found)


def read(db, user, center_id, doc_id, offset=0, limit=25):
    offset = v.integer(offset, 'Pagina', 0, 1_000_000)
    limit = v.integer(limit, 'Righe', 1, MAX_PAGE)
    with db.read() as con:
        user, _ = centers.scoped(con, user, center_id, 'hr.fascicoli')
        doc = _document(con, center_id, doc_id)
        state = current(con, doc)
        total = con.execute('SELECT count(*) FROM document_review_history WHERE document_id=?', (doc['id'],)).fetchone()[0]
        history = [dict(version=r['version'], status=r['status'], label=STATUSES[r['status']], note=r['note'], at=r['at'],
                        actor=r['actor'])
                   for r in con.execute('SELECT * FROM document_review_history WHERE document_id=? ORDER BY version DESC '
                                        'LIMIT ? OFFSET ?', (doc['id'], limit, offset))]
    return dict(document=doc, review=state, history=history, history_total=total, offset=offset, limit=limit,
                can_review=has(user, 'documenti.verifica'),
                can_resubmit=state['status'] == 'needs_correction' and has(user, 'documenti.ripresenta'))


def decide(db, actor, center_id, doc_id, raw):
    v.keys(raw, {'status', 'note', 'version'}, 'Verifica', required={'status', 'version'})
    status = v.choice(raw['status'], 'Esito', STATUSES, field='status')
    note = v.text(raw.get('note', ''), 'Nota', 2000, multiline=True, field='note')
    with db.write() as con:
        actor, _ = centers.scoped(con, actor, center_id, 'hr.fascicoli')
        doc = _document(con, center_id, doc_id)
        state = current(con, doc)
        if v.version(raw['version']) != state['version']:
            raise Conflict('Verifica aggiornata da un’altra sessione: riaprire il documento.')
        if status == state['status']:
            raise Invalid('Scegliere un nuovo esito: lo stato attuale è già registrato.', field='status')
        if status in ('verified', 'needs_correction'):
            if not has(actor, 'documenti.verifica'):
                raise Forbidden('La decisione sui documenti spetta a HR centrale e all’amministratore.')
        else:
            if not has(actor, 'documenti.ripresenta'):
                raise Forbidden('Ripresentazione non consentita a questo profilo.')
            if state['status'] != 'needs_correction':
                raise Invalid('Si può chiedere una nuova verifica solo per un documento da correggere.', field='status')
        if status in ('needs_correction', 'received') and len(note) < 8:
            raise Invalid('Descrivere la correzione o la nuova richiesta in almeno 8 caratteri.', field='note')
        if status == 'verified' and state['expired']:
            raise Invalid('Il documento è scaduto: caricare il rinnovo prima di verificarlo.', field='status')
        version = state['version'] + 1
        con.execute('''INSERT INTO document_reviews(document_id,status,note,version,updated_at,updated_by) VALUES(?,?,?,?,?,?)
                       ON CONFLICT(document_id) DO UPDATE SET status=excluded.status, note=excluded.note,
                       version=excluded.version, updated_at=excluded.updated_at, updated_by=excluded.updated_by''',
                    (doc['id'], status, note, version, stamp(), actor.username))
        con.execute('INSERT INTO document_review_history(document_id,version,status,note,at,actor) VALUES(?,?,?,?,?,?)',
                    (doc['id'], version, status, note, stamp(), actor.username))
        audit.record(con, actor, 'Verifica documento: ' + STATUSES[status].lower(), center_id, entity='document',
                     entity_id=doc['id'], before=dict(status=state['status'], version=state['version']),
                     after=dict(status=status, version=version, note=note, sha256=doc['sha256']))
    return read(db, actor, center_id, doc_id)


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


def _int(text, default):
    return int(text) if text.isdigit() else default


@route('GET', '/api/documents/<cid>/<doc_id>/review', cap='hr.fascicoli')
def api_read(ctx):
    return read(ctx.db, ctx.user, ctx.params['cid'], ctx.params['doc_id'], _int(ctx.q('offset'), 0), _int(ctx.q('limit'), 25))


@route('POST', '/api/documents/<cid>/<doc_id>/review', cap='hr.fascicoli')
def api_decide(ctx):
    return decide(ctx.db, ctx.user, ctx.params['cid'], ctx.params['doc_id'], ctx.body)
