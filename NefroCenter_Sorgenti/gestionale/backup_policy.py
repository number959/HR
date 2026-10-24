"""Separate, verified backup copies. No live restore, credentials or remote transfer.

The destination is an existing filesystem mount managed by the server operator.
This module cannot establish whether that mount is physically remote. Configuration
and status are server-side JSON files; the original daily backups are never pruned.
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
from datetime import datetime, timezone, timedelta
from pathlib import Path

import backup_tools

LOG = logging.getLogger(__name__)
LOCK = threading.RLock()
DEFAULTS = dict(enabled=False, destination='', retention_count=0, probe_interval_days=30)
CONFIG = 'backup_policy.json'
STATE = 'backup_status.json'
COPY_NAME = re.compile(r'copia_\d{8}T\d{12}Z_[a-f0-9]{12}')


def _now():
    return datetime.now(timezone.utc)


def _stamp():
    return _now().isoformat(timespec='seconds')


def _safe_path(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Usare un percorso assoluto senza componenti "..".')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('I percorsi dei backup non possono contenere collegamenti simbolici.')
    return path


def _load(path, default):
    _safe_path(path)
    if not path.exists():
        return dict(default)
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('File di configurazione o stato backup non valido.')
    with path.open(encoding='utf-8') as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError('Configurazione o stato backup non valido.')
    return value


def _atomic_json(path, value):
    _safe_path(path)
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


def _root(core):
    return _safe_path(core.DB.absolute().parent)


def _destination(core, value, must_exist=True):
    if not isinstance(value, str) or len(value) > 2048 or '\x00' in value:
        raise ValueError('Destinazione backup non valida.')
    path = _safe_path(Path(value))
    if must_exist and not path.is_dir():
        raise ValueError('La destinazione deve essere una cartella esistente e montata sul server.')
    root = _root(core).resolve()
    real = path.resolve()
    if real == root or root in real.parents or real in root.parents:
        raise ValueError('Scegliere una cartella separata dalla cartella dati e dai backup originali.')
    return path


def _config(core):
    value = {**DEFAULTS, **_load(_root(core) / CONFIG, {})}
    if type(value['enabled']) is not bool:
        raise ValueError('Attivazione backup non valida.')
    if type(value['retention_count']) is not int or not 0 <= value['retention_count'] <= 10000:
        raise ValueError('Conservazione: da 1 a 10000 copie; 0 disattiva la cancellazione.')
    if type(value['probe_interval_days']) is not int or not 1 <= value['probe_interval_days'] <= 365:
        raise ValueError('Prova di ripristino: intervallo da 1 a 365 giorni.')
    if not isinstance(value['destination'], str):
        raise ValueError('Destinazione backup non valida.')
    if value.get('installation_id') and not re.fullmatch('[a-f0-9]{32}', value['installation_id']):
        raise ValueError('Identificativo installazione backup non valido.')
    return value


def _state(core):
    return _load(_root(core) / STATE, {'copies': []})


def _public(core, config, state):
    out = {key: config[key] for key in DEFAULTS}
    out.update(last_attempt=state.get('last_attempt'), last_success=state.get('last_success'),
               last_error=state.get('last_error', ''), retention_error=state.get('retention_error', ''),
               last_probe=state.get('last_probe'), last_copy=state.get('last_copy'),
               copy_count=sum(c.get('destination') == config['destination'] for c in state.get('copies', [])),
               schedule='Una copia al giorno; controllo ogni ora mentre il servizio è attivo.',
               protection_note='Una cartella separata non garantisce protezione da guasti del server. '
               'Il tecnico deve predisporre un volume indipendente o una condivisione aziendale e verificarne il montaggio. '
               'La chiave 2FA e la configurazione del server vanno conservate separatamente.',
               same_filesystem=None)
    if config['destination']:
        try:
            destination = _destination(core, config['destination'])
            out['same_filesystem'] = destination.stat().st_dev == _root(core).stat().st_dev
        except (OSError, ValueError) as exc:
            out['destination_error'] = str(exc)
    return out


def status(core, user):
    """Web read API. Paths and operational errors are visible only to a fresh admin."""
    backup_tools.require_admin(core, user)
    with LOCK:
        return _public(core, _config(core), _state(core))


def console_status(core):
    with LOCK:
        return _public(core, _config(core), _state(core))


def configure(core, settings, user=None):
    """Call from local console, or from an admin endpoint AFTER recent 2FA step-up."""
    if user is not None:
        backup_tools.require_admin(core, user)
    if not isinstance(settings, dict) or set(settings) - set(DEFAULTS):
        raise ValueError('Impostazioni backup non riconosciute.')
    with LOCK:
        old = _config(core)
        cfg = {**old, **settings}
        if type(cfg['enabled']) is not bool:
            raise ValueError('Attivazione backup non valida.')
        for key, low, high in [('retention_count', 0, 10000), ('probe_interval_days', 1, 365)]:
            if type(cfg[key]) is not int or not low <= cfg[key] <= high:
                raise ValueError('Valore non valido: ' + key)
        if not isinstance(cfg['destination'], str):
            raise ValueError('Destinazione backup non valida.')
        if cfg['destination'] or cfg['enabled']:
            cfg['destination'] = str(_destination(core, cfg['destination'], must_exist=cfg['enabled']))
        cfg.setdefault('installation_id', secrets.token_hex(16))
        state = _state(core)
        if cfg['destination'] != old['destination']:
            for key in ('last_success', 'last_copy', 'last_probe', 'last_error', 'retention_error'):
                state.pop(key, None)
            _atomic_json(_root(core) / STATE, state)
        _atomic_json(_root(core) / CONFIG, cfg)
        if user is not None:
            with core.connect() as conn:
                core.audit(conn, user, 'Configurazione copie backup', before={k: old[k] for k in DEFAULTS},
                           after={k: cfg[k] for k in DEFAULTS})
                conn.commit()
        return _public(core, cfg, state)


def _digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect(path):
    """Read a completed standalone database, including every HR document hash."""
    _safe_path(path)
    # closing(): the read-only file must be released before the temporary probe copy is deleted.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as conn:
        if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Integrità SQLite non superata.')
        if conn.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('Relazioni del database non valide.')
        required = {'users', 'centers', 'people', 'entries', 'hr_documents'}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= tables:
            raise ValueError('Il backup non contiene tutte le tabelle applicative richieste.')
        counts = {table: conn.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in sorted(required)}
        documents_bytes = 0
        for expected, content in conn.execute('SELECT sha256,content FROM hr_documents'):
            if not isinstance(content, bytes) or hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('Impronta di un allegato HR non valida.')
            documents_bytes += len(content)
        return dict(rows=counts, documents_bytes=documents_bytes)


def _copy_file(source, target):
    # Exclusive destination creation, permissions independent of the server umask.
    handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(handle, 'wb') as output, source.open('rb') as input_file:
        shutil.copyfileobj(input_file, output, length=1024 * 1024)
        output.flush()
        os.fsync(output.fileno())


def _managed(core, cfg):
    destination = _destination(core, cfg['destination'])
    root = destination / ('NefroCenter-backups-' + cfg['installation_id'])
    _safe_path(root)
    owner = root / '.owner.json'
    if root.exists():
        if not root.is_dir() or _load(owner, {}) != {'installation_id': cfg['installation_id']}:
            raise ValueError('La cartella di destinazione non è riconosciuta come gestita da questa installazione.')
    else:
        root.mkdir(mode=0o700)
        _atomic_json(owner, {'installation_id': cfg['installation_id']})
    return root


def _probe(source, expected, core):
    """Restore into an isolated temporary copy, without loading Auth or starting HTTP."""
    with tempfile.TemporaryDirectory(prefix='.backup-prova-', dir=_root(core)) as directory:
        restored = Path(directory) / 'ripristino.sqlite3'
        _copy_file(source, restored)
        if _digest(restored) != expected:
            raise ValueError('La copia di prova differisce dal backup verificato.')
        result = _inspect(restored)
        return dict(at=_stamp(), ok=True, **result,
                    detail='Copia temporanea: integrità SQLite, relazioni e impronte di tutti gli allegati HR verificate. '
                    'Nessun account attivato o server avviato; copia temporanea rimossa.')


def _prune(core, cfg, state, managed):
    """Only indexed, unchanged copies created here; called after new verified publish."""
    keep = cfg['retention_count']
    if not keep:
        return
    candidates = [item for item in state['copies'] if item.get('destination') == cfg['destination']]
    for item in candidates[:-max(1, keep)]:
        name = item.get('folder', '')
        if not COPY_NAME.fullmatch(name):
            raise ValueError('Conservazione sospesa: nome copia non riconosciuto.')
        directory = _safe_path(managed / name)
        if not directory.exists():
            state['copies'].remove(item)
            continue
        database = _safe_path(directory / 'presenze.sqlite3')
        manifest = _load(directory / 'manifest.json', {})
        if (not directory.is_dir() or not database.is_file()
                or set(p.name for p in directory.iterdir()) != {'presenze.sqlite3', 'manifest.json'}
                or manifest.get('installation_id') != cfg['installation_id']
                or manifest.get('sha256') != item.get('sha256') or _digest(database) != item.get('sha256')):
            raise ValueError('Conservazione sospesa: una vecchia copia è cambiata o contiene file non gestiti.')
        # No recursive removal: unfamiliar files and symlinks are never followed.
        database.unlink()
        (directory / 'manifest.json').unlink()
        directory.rmdir()
        state['copies'].remove(item)


def run(core, force=False, probe=False):
    """Internal scheduler/console API. Errors are persisted and raised for server logs."""
    with LOCK:
        cfg = _config(core)
        state = _state(core)
        if not cfg['enabled']:
            return _public(core, cfg, state)
        if not force and state.get('last_success', '')[:10] == _stamp()[:10]:
            return _public(core, cfg, state)
        state['last_attempt'] = _stamp()
        pending = None
        try:
            if not cfg.get('installation_id'):
                raise ValueError('Salvare la configurazione backup prima di attivarla.')
            source_dir = _safe_path(_root(core) / 'backups')
            sources = sorted(backup_tools.completed_files(source_dir), key=lambda p: p.name)
            if not sources:
                raise ValueError('Nessun backup originale completato disponibile. Creare prima un backup locale.')
            source = _safe_path(sources[-1].absolute())
            if source == core.DB.absolute() or source.stat().st_nlink != 1:
                raise ValueError('La sorgente deve essere una copia autonoma, non il database attivo.')
            summary = _inspect(source)
            digest = _digest(source)
            managed = _managed(core, cfg)
            pending = Path(tempfile.mkdtemp(prefix='.pending-', dir=managed))
            target = pending / 'presenze.sqlite3'
            _copy_file(source, target)
            if _digest(target) != digest or _digest(source) != digest or _inspect(target) != summary:
                raise ValueError('La copia non corrisponde al backup originale verificato.')
            last_probe = state.get('last_probe') or {}
            probe_due = not last_probe.get('ok') or not last_probe.get('at')
            if not probe_due:
                probe_due = _now() - datetime.fromisoformat(last_probe['at']) >= timedelta(days=cfg['probe_interval_days'])
            if probe or probe_due:
                try:
                    state['last_probe'] = _probe(target, digest, core)
                except Exception as exc:
                    state['last_probe'] = dict(at=_stamp(), ok=False, detail=str(exc))
                    raise
            folder = 'copia_' + _now().strftime('%Y%m%dT%H%M%S%fZ') + '_' + secrets.token_hex(6)
            manifest = dict(installation_id=cfg['installation_id'], created_at=_stamp(), source=source.name,
                            sha256=digest, bytes=target.stat().st_size, **summary)
            _atomic_json(pending / 'manifest.json', manifest)
            os.replace(pending, managed / folder)
            pending = None
            record = dict(folder=folder, destination=cfg['destination'], **manifest)
            state.setdefault('copies', []).append(record)
            state.update(last_success=_stamp(), last_error='', retention_error='', last_copy=record)
            # Persist ownership before any pruning. Failure here leaves safe, untracked copies.
            _atomic_json(_root(core) / STATE, state)
            try:
                _prune(core, cfg, state, managed)
            except Exception as exc:
                state['retention_error'] = str(exc)
                LOG.warning('Conservazione backup sospesa: %s', exc)
            _atomic_json(_root(core) / STATE, state)
            return _public(core, cfg, state)
        except Exception as exc:
            state['last_error'] = str(exc)
            _atomic_json(_root(core) / STATE, state)
            raise
        finally:
            if pending is not None and pending.exists():
                shutil.rmtree(pending)


def run_admin(core, user, probe=False):
    """Fresh local snapshot then verified separate copy; route must enforce step-up."""
    backup_tools.require_admin(core, user)
    with LOCK:
        if not _config(core)['enabled']:
            raise ValueError('Configurare e attivare prima la copia su destinazione separata.')
        core._backup()
        result = run(core, force=True, probe=probe)
        with core.connect() as conn:
            core.audit(conn, user, 'Copia backup separata verificata', after={'probe': probe})
            conn.commit()
        return result
