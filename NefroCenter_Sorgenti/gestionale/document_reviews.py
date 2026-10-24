"""Human HR review of immutable personnel attachments.

An expiry remains a date-derived warning; it never rewrites a recorded decision.
The full history is restricted to authorized HR users and bounded on every read.
"""
from datetime import date
import re

STATUSES = {'received': 'Ricevuto · da verificare', 'needs_correction': 'Da correggere',
            'verified': 'Verificato da HR'}
MAX_HISTORY = 100


def init(app):
    with app.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS hr_document_reviews(
            document_id TEXT PRIMARY KEY REFERENCES hr_documents(id) ON DELETE CASCADE,
            version INTEGER NOT NULL, status TEXT NOT NULL,
            note TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hr_document_review_history(
            document_id TEXT NOT NULL REFERENCES hr_documents(id) ON DELETE CASCADE,
            version INTEGER NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL,
            stamp TEXT NOT NULL, actor TEXT NOT NULL,
            PRIMARY KEY(document_id,version)
        );
        ''')
        # Existing files have no human validation. Their fallback remains received,
        # version 0; migrations must never imply that HR checked their contents.
        c.commit()


def _text(value, maximum=200):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise ValueError('Testo non valido o troppo lungo.')
    return value.strip()


def _access(app, c, user, cid, docid):
    cid = _text(cid, 80); docid = _text(docid, 80)
    if not cid or not docid:
        raise ValueError('Documento e centro obbligatori.')
    user = app.fresh_user(c, user)
    app.require_hr(user, cid)
    row = c.execute('''SELECT id,cid,pid,name,category,expiry,uploaded_at,uploaded_by,
        sha256,length(content) AS size FROM hr_documents WHERE id=? AND cid=?''',
                    (docid, cid)).fetchone()
    if not row:
        raise ValueError('Documento non trovato nel centro.')
    return user, dict(row)


def metadata(c, doc, today=None):
    """Internal helper: caller must already authorize this document's center."""
    current = c.execute('SELECT * FROM hr_document_reviews WHERE document_id=?',
                        (doc['id'],)).fetchone()
    expiry = doc.get('expiry', '')
    today = today or date.today().isoformat()
    result = (dict(current) if current else {
        'version': 0, 'status': 'received', 'note': '',
        'updated_at': doc.get('uploaded_at', ''), 'updated_by': doc.get('uploaded_by', '')})
    result.pop('document_id', None)
    result['label'] = STATUSES[result['status']]
    result['expired'] = bool(expiry and expiry < today)
    result['effective_status'] = 'expired' if result['expired'] else result['status']
    return result


def attach(c, document, today=None):
    document = dict(document)
    document['review'] = metadata(c, document, today)
    return document


def registered(app, c, user, docid):
    """Record a new file on the upload transaction; no additional connection."""
    stamp = app.now()
    c.execute('INSERT INTO hr_document_reviews VALUES(?,?,?,?,?,?)',
              (docid, 1, 'received', '', stamp, user['username']))
    c.execute('INSERT INTO hr_document_review_history VALUES(?,?,?,?,?,?)',
              (docid, 1, 'received', '', stamp, user['username']))


def _pagination(offset, limit):
    # GET query parameters are strings; bools and floats are never valid versions.
    def integer(v):
        if type(v) is int:
            return v
        if isinstance(v, str) and re.fullmatch(r'\d{1,7}', v):
            return int(v)
        raise ValueError('Pagina dello storico non valida.')
    offset, limit = integer(offset), integer(limit)
    if not 0 <= offset <= 1000000 or not 1 <= limit <= MAX_HISTORY:
        raise ValueError('Pagina dello storico non valida.')
    return offset, limit


def read(app, user, cid, docid, offset=0, limit=25):
    offset, limit = _pagination(offset, limit)
    with app.connect() as c:
        user, doc = _access(app, c, user, cid, docid)
        current = metadata(c, doc)
        total = c.execute('SELECT count(*) FROM hr_document_review_history WHERE document_id=?',
                          (docid,)).fetchone()[0]
        history = [dict(r) for r in c.execute('''SELECT version,status,note,stamp,actor
            FROM hr_document_review_history WHERE document_id=? ORDER BY version DESC LIMIT ? OFFSET ?''',
                                            (docid, limit, offset))]
    return {'document': doc, 'review': current, 'history': history,
            'history_total': total, 'offset': offset, 'limit': limit,
            'can_review': user['role'] in ('admin', 'hr'),
            'can_resubmit': current['status'] == 'needs_correction',
            'legacy_unreviewed': current['version'] == 0}


def review(app, user, body):
    if not isinstance(body, dict):
        raise ValueError('Richiesta di verifica non valida.')
    cid, docid = body.get('cid', ''), body.get('id', '')
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        user, doc = _access(app, c, user, cid, docid)
        current = metadata(c, doc)
        version = body.get('version')
        if type(version) is not int or version != current['version']:
            raise ValueError('Verifica aggiornata da un’altra sessione. Riapri il documento.')
        status = body.get('status')
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError('Esito della verifica non valido.')
        note = _text(body.get('note', ''), 2000)
        if status == current['status']:
            raise ValueError('Scegli un nuovo esito; lo stato corrente è già registrato.')
        if status in ('verified', 'needs_correction'):
            if user['role'] not in ('admin', 'hr'):
                raise PermissionError('La decisione sui documenti è riservata a HR centrale e amministratori.')
        elif current['status'] != 'needs_correction':
            raise ValueError('Puoi richiedere una nuova verifica soltanto per un documento da correggere.')
        if status in ('needs_correction', 'received') and len(note) < 8:
            raise ValueError('Descrivi la correzione o la richiesta di nuova verifica in almeno 8 caratteri.')
        if status == 'verified' and current['expired']:
            raise ValueError('Il documento è scaduto. Carica il rinnovo prima della verifica.')
        stamp = app.now(); next_version = current['version'] + 1
        c.execute('''INSERT INTO hr_document_reviews VALUES(?,?,?,?,?,?)
            ON CONFLICT(document_id) DO UPDATE SET version=excluded.version,status=excluded.status,
            note=excluded.note,updated_at=excluded.updated_at,updated_by=excluded.updated_by''',
                  (docid, next_version, status, note, stamp, user['username']))
        c.execute('INSERT INTO hr_document_review_history VALUES(?,?,?,?,?,?)',
                  (docid, next_version, status, note, stamp, user['username']))
        # Audit remains after a file is removed. The active history rows cascade
        # with the file, so a deleted document cannot be reopened through this API.
        app.audit(c, user, 'Verifica documento HR aggiornata', cid,
                  before={'document_id': docid, 'version': current['version'], 'status': current['status']},
                  after={'document_id': docid, 'pid': doc['pid'], 'version': next_version,
                         'status': status, 'note': note, 'sha256': doc['sha256']})
        c.commit()
    return {'ok': True, **read(app, user, cid, docid)}
