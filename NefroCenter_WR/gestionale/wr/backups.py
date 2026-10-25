"""Backup dell'archivio e seconda copia verificata su una cartella separata (per esempio un NAS).

- Il backup locale è una copia coerente dell'archivio (API di backup di SQLite),
  creata una volta al giorno mentre il servizio è attivo e su richiesta.
- La seconda copia è disattivata finché l'amministratore non indica una cartella
  esistente e già montata sul server: il programma non gestisce credenziali di
  rete e non può sapere se la cartella si trova fisicamente altrove.
- Ogni copia viene verificata (integrità, relazioni, impronte di tutti gli
  allegati); periodicamente si prova un ripristino su una copia temporanea.
- Nessun ripristino via web e nessuna cancellazione dei backup originali.
"""
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import audit, users
from .errors import Invalid, NotFound
from .permissions import require
from .web import Reply

LOG = logging.getLogger('wr.backups')
LOCK = threading.RLock()
LOCAL = re.compile(r'wr_\d{8}_\d{6}_\d{6}\.sqlite3')
COPY = re.compile(r'copia_\d{8}T\d{12}Z_[a-f0-9]{12}')
MAX_DOWNLOAD = 256 * 1024 * 1024
DEFAULTS = dict(enabled=False, destination='', retention_count=0, probe_interval_days=30)
POLICY = 'backup_policy.json'
STATUS = 'backup_status.json'
REQUIRED_TABLES = {'users', 'centers', 'people', 'entries', 'documents'}
NOTE = ('Una cartella separata non protegge da tutti i guasti: il tecnico deve predisporre un volume indipendente o una '
        'condivisione aziendale e verificarne il montaggio. La chiave del server va conservata a parte, in modo protetto.')


def _now():
    return datetime.now(timezone.utc)


def _stamp():
    return _now().isoformat(timespec='seconds')


def safe_path(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise Invalid('Usare un percorso assoluto senza componenti «..».', field='destination')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Invalid('I percorsi dei backup non possono contenere collegamenti simbolici.', field='destination')
    return path


def root(db):
    return safe_path(db.path.absolute().parent)


def local_dir(db):
    return root(db) / 'backups'


def _load(path, default):
    if not path.exists():
        return dict(default)
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise Invalid('File di configurazione dei backup non valido.')
    with path.open(encoding='utf-8') as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise Invalid('File di configurazione dei backup non valido.')
    return value


def _save(path, value):
    handle, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as target:
            json.dump(value, target, ensure_ascii=False, indent=2)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def completed(directory):
    """Backup locali completati: nome atteso, file normale, intestazione SQLite."""
    if not directory.exists():
        return
    for path in directory.iterdir():
        if not LOCAL.fullmatch(path.name) or path.is_symlink() or not path.is_file():
            continue
        try:
            with path.open('rb') as source:
                if source.read(16) != b'SQLite format 3\x00':
                    continue
        except FileNotFoundError:
            continue
        yield path


def create(db, reason='manuale'):
    with LOCK:
        return db.snapshot(reason=reason, directory=local_dir(db))


def daily(db):
    """Un backup al giorno: crea la copia solo se oggi non ne esiste già una."""
    prefix = 'wr_' + datetime.now().strftime('%Y%m%d') + '_'
    if not any(p.name.startswith(prefix) for p in completed(local_dir(db))):
        return create(db, 'giornaliero')
    return None


def listing(db, user):
    with db.read() as con:
        require(users.reload(con, user), 'backup.gestisci')
    files = []
    for path in completed(local_dir(db)):
        st = path.stat()
        files.append(dict(filename=path.name, bytes=st.st_size, downloadable=st.st_size <= MAX_DOWNLOAD,
                          created_at=datetime.fromtimestamp(st.st_mtime).astimezone().isoformat(timespec='seconds')))
    files.sort(key=lambda f: f['filename'], reverse=True)
    return dict(files=files[:50], count=len(files), bytes=sum(f['bytes'] for f in files), shown=min(50, len(files)),
                schedule='Un backup al giorno mentre il servizio è attivo, con controllo ogni ora.', policy=status(db))


def create_admin(db, actor):
    with db.read() as con:
        require(users.reload(con, actor), 'backup.gestisci')
    path = create(db)
    with db.write() as con:
        audit.record(con, users.reload(con, actor), 'Backup creato', entity='backup', entity_id=path.name)
    return dict(filename=path.name)


def download(db, actor, filename):
    with db.read() as con:
        require(users.reload(con, actor), 'backup.gestisci')
    if not isinstance(filename, str) or not LOCAL.fullmatch(filename):
        raise Invalid('Nome del backup non valido.')
    directory = local_dir(db)
    path = directory / filename
    if path.is_symlink() or not path.is_file() or path.resolve().parent != directory.resolve():
        raise NotFound('Backup non disponibile.')
    if path.stat().st_size > MAX_DOWNLOAD:
        raise Invalid('Backup oltre 256 MiB: copiarlo direttamente dal server.')
    content = path.read_bytes()
    if not content.startswith(b'SQLite format 3\x00'):
        raise Invalid('Il file non è un archivio SQLite valido.')
    with db.write() as con:
        audit.record(con, users.reload(con, actor), 'Backup scaricato', entity='backup', entity_id=filename)
    return Reply(content, content_type='application/vnd.sqlite3', filename=filename)


# --- seconda copia ---------------------------------------------------------------------------

def _destination(db, value, must_exist=True):
    if not isinstance(value, str) or len(value) > 2048 or '\x00' in value:
        raise Invalid('Cartella di destinazione non valida.', field='destination')
    path = safe_path(value)
    if must_exist and not path.is_dir():
        raise Invalid('La destinazione deve essere una cartella esistente e montata sul server.', field='destination')
    base = root(db).resolve()
    real = path.resolve()
    if real == base or base in real.parents or real in base.parents:
        raise Invalid('Scegliere una cartella separata dalla cartella dei dati e dai backup originali.', field='destination')
    return path


def policy(db):
    value = {**DEFAULTS, **_load(root(db) / POLICY, {})}
    return value


def _state(db):
    return _load(root(db) / STATUS, {'copies': []})


def _public(db, cfg, state):
    out = {k: cfg[k] for k in DEFAULTS}
    out.update(last_attempt=state.get('last_attempt'), last_success=state.get('last_success'),
               last_error=state.get('last_error', ''), retention_error=state.get('retention_error', ''),
               last_probe=state.get('last_probe'), last_copy=state.get('last_copy'),
               copy_count=sum(c.get('destination') == cfg['destination'] for c in state.get('copies', [])),
               schedule='Una copia al giorno; controllo ogni ora mentre il servizio è attivo.', note=NOTE,
               same_filesystem=None)
    if cfg['destination']:
        try:
            out['same_filesystem'] = _destination(db, cfg['destination']).stat().st_dev == root(db).stat().st_dev
        except (OSError, Invalid) as exc:
            out['destination_error'] = getattr(exc, 'message', str(exc))
    return out


def status(db):
    with LOCK:
        return _public(db, policy(db), _state(db))


def last_problem(db):
    try:
        state = _state(db)
    except Exception as exc:  # pragma: no cover - file danneggiato
        return str(exc)
    return state.get('last_error') or state.get('retention_error') or ''


def configure(db, settings, actor=None):
    """Da console o dall'amministratore con conferma di sicurezza recente."""
    if not isinstance(settings, dict) or set(settings) - set(DEFAULTS):
        raise Invalid('Impostazioni dei backup non riconosciute.')
    with LOCK:
        old = policy(db)
        cfg = {**old, **settings}
        if type(cfg['enabled']) is not bool:
            raise Invalid('Attivazione non valida.', field='enabled')
        for key, low, high in (('retention_count', 0, 10000), ('probe_interval_days', 1, 365)):
            if type(cfg[key]) is not int or not low <= cfg[key] <= high:
                raise Invalid(f'Valore non valido: {key}.', field=key)
        if cfg['destination'] or cfg['enabled']:
            cfg['destination'] = str(_destination(db, cfg['destination'], must_exist=cfg['enabled']))
        cfg.setdefault('installation_id', secrets.token_hex(16))
        state = _state(db)
        if cfg['destination'] != old['destination']:
            for key in ('last_success', 'last_copy', 'last_probe', 'last_error', 'retention_error'):
                state.pop(key, None)
            _save(root(db) / STATUS, state)
        _save(root(db) / POLICY, cfg)
        if actor is not None:
            with db.write() as con:
                audit.record(con, users.reload(con, actor), 'Seconda copia dei backup configurata', entity='backup_policy',
                             before={k: old[k] for k in DEFAULTS}, after={k: cfg[k] for k in DEFAULTS})
        return _public(db, cfg, state)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inspect(path):
    """Controlla una copia autonoma: integrità, relazioni, tabelle e impronte di tutti gli allegati."""
    with closing(sqlite3.connect(Path(path).as_uri() + '?mode=ro&immutable=1', uri=True)) as con:
        if con.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise Invalid('Integrità SQLite non superata.')
        if con.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise Invalid('Relazioni dell’archivio non valide.')
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED_TABLES <= tables:
            raise Invalid('Il backup non contiene tutte le tabelle del portale.')
        counts = {t: con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in sorted(REQUIRED_TABLES)}
        size = 0
        for expected, content in con.execute('SELECT sha256, content FROM documents'):
            if not isinstance(content, bytes) or hashlib.sha256(content).hexdigest() != expected:
                raise Invalid('Impronta di un allegato non valida.')
            size += len(content)
        return dict(rows=counts, documents_bytes=size)


def _copy(source, target):
    handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(handle, 'wb') as out, source.open('rb') as src:
        shutil.copyfileobj(src, out, length=1024 * 1024)
        out.flush()
        os.fsync(out.fileno())


def _managed(db, cfg):
    folder = _destination(db, cfg['destination']) / ('NefroCenter-WR-backups-' + cfg['installation_id'])
    owner = folder / '.owner.json'
    if folder.exists():
        if not folder.is_dir() or _load(owner, {}) != {'installation_id': cfg['installation_id']}:
            raise Invalid('La cartella di destinazione non risulta gestita da questa installazione.')
    else:
        folder.mkdir(mode=0o700)
        _save(owner, {'installation_id': cfg['installation_id']})
    return folder


def _probe(db, source, expected):
    with tempfile.TemporaryDirectory(prefix='.prova-ripristino-', dir=root(db)) as directory:
        restored = Path(directory) / 'ripristino.sqlite3'
        _copy(source, restored)
        if digest(restored) != expected:
            raise Invalid('La copia di prova differisce dal backup verificato.')
        result = inspect(restored)
    return dict(at=_stamp(), ok=True, detail='Ripristino di prova su copia temporanea: integrità, relazioni e impronte di '
                                             'tutti gli allegati verificate; copia temporanea eliminata.', **result)


def _prune(db, cfg, state, managed):
    keep = cfg['retention_count']
    if not keep:
        return
    mine = [c for c in state['copies'] if c.get('destination') == cfg['destination']]
    for item in mine[:-max(1, keep)]:
        name = item.get('folder', '')
        if not COPY.fullmatch(name):
            raise Invalid('Conservazione sospesa: nome di copia non riconosciuto.')
        directory = safe_path(managed / name)
        if not directory.exists():
            state['copies'].remove(item)
            continue
        database = directory / 'wr.sqlite3'
        manifest = _load(directory / 'manifest.json', {})
        if (not directory.is_dir() or not database.is_file()
                or {p.name for p in directory.iterdir()} != {'wr.sqlite3', 'manifest.json'}
                or manifest.get('installation_id') != cfg['installation_id'] or manifest.get('sha256') != item.get('sha256')
                or digest(database) != item.get('sha256')):
            raise Invalid('Conservazione sospesa: una copia precedente è cambiata o contiene file non gestiti.')
        database.unlink()
        (directory / 'manifest.json').unlink()
        directory.rmdir()
        state['copies'].remove(item)


def run(db, force=False, probe=False):
    """Seconda copia del backup più recente (pianificatore e console)."""
    with LOCK:
        cfg = policy(db)
        state = _state(db)
        if not cfg['enabled']:
            return _public(db, cfg, state)
        if not force and (state.get('last_success') or '')[:10] == _stamp()[:10]:
            return _public(db, cfg, state)
        state['last_attempt'] = _stamp()
        pending = None
        try:
            if not cfg.get('installation_id'):
                raise Invalid('Salvare la configurazione prima di attivarla.')
            sources = sorted(completed(local_dir(db)), key=lambda p: p.name)
            if not sources:
                raise Invalid('Nessun backup locale completato: crearne prima uno.')
            source = safe_path(sources[-1].absolute())
            if source == db.path.absolute() or source.stat().st_nlink != 1:
                raise Invalid('La sorgente deve essere una copia autonoma, non l’archivio attivo.')
            summary = inspect(source)
            expected = digest(source)
            managed = _managed(db, cfg)
            pending = Path(tempfile.mkdtemp(prefix='.in-corso-', dir=managed))
            target = pending / 'wr.sqlite3'
            _copy(source, target)
            if digest(target) != expected or inspect(target) != summary:
                raise Invalid('La copia non corrisponde al backup originale verificato.')
            last_probe = state.get('last_probe') or {}
            due = not last_probe.get('ok') or not last_probe.get('at') or (
                _now() - datetime.fromisoformat(last_probe['at']) >= timedelta(days=cfg['probe_interval_days']))
            if probe or due:
                try:
                    state['last_probe'] = _probe(db, target, expected)
                except Exception as exc:
                    state['last_probe'] = dict(at=_stamp(), ok=False, detail=getattr(exc, 'message', str(exc)))
                    raise
            folder = 'copia_' + _now().strftime('%Y%m%dT%H%M%S%fZ') + '_' + secrets.token_hex(6)
            manifest = dict(installation_id=cfg['installation_id'], created_at=_stamp(), source=source.name, sha256=expected,
                            bytes=target.stat().st_size, **summary)
            _save(pending / 'manifest.json', manifest)
            os.replace(pending, managed / folder)
            pending = None
            record = dict(folder=folder, destination=cfg['destination'], **manifest)
            state.setdefault('copies', []).append(record)
            state.update(last_success=_stamp(), last_error='', retention_error='', last_copy=record)
            _save(root(db) / STATUS, state)
            try:
                _prune(db, cfg, state, managed)
            except Exception as exc:
                state['retention_error'] = getattr(exc, 'message', str(exc))
                LOG.warning('Conservazione delle copie sospesa: %s', state['retention_error'])
            _save(root(db) / STATUS, state)
            return _public(db, cfg, state)
        except Exception as exc:
            state['last_error'] = getattr(exc, 'message', str(exc))
            _save(root(db) / STATUS, state)
            raise
        finally:
            if pending is not None and pending.exists():
                shutil.rmtree(pending)


def run_admin(db, actor, probe=False):
    with db.read() as con:
        require(users.reload(con, actor), 'backup.gestisci')
    with LOCK:
        if not policy(db)['enabled']:
            raise Invalid('Configurare e attivare prima la seconda copia su una cartella separata.')
        create(db, 'prima-della-copia')
        result = run(db, force=True, probe=probe)
    with db.write() as con:
        audit.record(con, users.reload(con, actor), 'Seconda copia dei backup verificata', entity='backup_policy',
                     after=dict(probe=probe))
    return result


def scheduled(db):
    """Chiamata ogni ora dal servizio: backup giornaliero e, se attiva, seconda copia."""
    try:
        daily(db)
    except Exception:
        LOG.exception('Backup giornaliero non riuscito')
    try:
        run(db)
    except Exception:
        LOG.exception('Seconda copia dei backup non riuscita')


# --- API ------------------------------------------------------------------------------------
from .web import route  # noqa: E402


@route('GET', '/api/backups', cap='backup.gestisci')
def api_list(ctx):
    return listing(ctx.db, ctx.user)


@route('POST', '/api/backups', cap='backup.gestisci', step_up=True)
def api_create(ctx):
    return create_admin(ctx.db, ctx.user)


@route('GET', '/api/backups/files/<name>', cap='backup.gestisci', step_up=True)
def api_download(ctx):
    return download(ctx.db, ctx.user, ctx.params['name'])


@route('PUT', '/api/backups/policy', cap='backup.gestisci', step_up=True)
def api_policy(ctx):
    return configure(ctx.db, ctx.body, ctx.user)


@route('POST', '/api/backups/policy/run', cap='backup.gestisci', step_up=True)
def api_run(ctx):
    return run_admin(ctx.db, ctx.user, probe=ctx.body.get('probe') is True)
