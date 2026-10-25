"""Accesso al database SQLite: connessioni, transazioni e aggiornamento dello schema.

Regole:
- ogni scrittura avviene in una transazione BEGIN IMMEDIATE (una sola scrittura per volta);
- le letture usano una transazione per vedere dati coerenti fra più query;
- prima di aggiornare uno schema esistente si crea una copia di sicurezza;
- un archivio della vecchia versione 0.11 non viene mai modificato.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import SCHEMA_VERSION
from .schema import LEGACY_TABLES, MIGRATIONS
from .util import stamp


class LegacyArchive(RuntimeError):
    """L'archivio indicato appartiene alla versione 0.11 e va migrato, non aperto."""


class Database:
    def __init__(self, path, *, wal=True):
        self.path = Path(path)
        self.wal = wal

    def connect(self):
        con = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        return con

    @contextmanager
    def read(self):
        """Lettura coerente: tutte le query vedono lo stesso istante dell'archivio."""
        con = self.connect()
        try:
            con.execute('BEGIN')
            yield con
        finally:
            try:
                if con.in_transaction:
                    con.execute('ROLLBACK')
            finally:
                con.close()

    @contextmanager
    def write(self):
        """Scrittura atomica: tutto o niente."""
        con = self.connect()
        try:
            con.execute('BEGIN IMMEDIATE')
            yield con
            con.execute('COMMIT')
        except BaseException:
            if con.in_transaction:
                con.execute('ROLLBACK')
            raise
        finally:
            con.close()

    def schema_version(self):
        if not self.path.exists():
            return 0
        con = self.connect()
        try:
            return con.execute('PRAGMA user_version').fetchone()[0]
        finally:
            con.close()

    def is_legacy(self):
        if not self.path.exists():
            return False
        con = sqlite3.connect(f'file:{self.path.as_posix()}?mode=ro', uri=True)
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
        return bool(LEGACY_TABLES & tables) and 'identities' not in tables

    def migrate(self):
        """Crea o aggiorna lo schema. Restituisce la versione finale."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.is_legacy():
            raise LegacyArchive(
                'Questo archivio appartiene alla versione 0.11 (Persone e Presenze Web). '
                'Non viene modificato: usare "python manage.py migra-011" per creare un nuovo archivio WR.')
        current = self.schema_version()
        if current > SCHEMA_VERSION:
            raise RuntimeError('Archivio creato da una versione più recente di NefroCenter WR: aggiornare il programma.')
        if current and current < SCHEMA_VERSION:
            self.snapshot(reason=f'prima-aggiornamento-schema-{current}')
        con = self.connect()
        try:
            if self.wal:
                con.execute('PRAGMA journal_mode=WAL')
            for version in range(current + 1, SCHEMA_VERSION + 1):
                con.execute('BEGIN IMMEDIATE')
                try:
                    for statement in _statements(MIGRATIONS[version]):
                        con.execute(statement)
                    con.execute(f'PRAGMA user_version={version}')
                    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_updated_at',?)", (stamp(),))
                    con.execute('COMMIT')
                except BaseException:
                    con.execute('ROLLBACK')
                    raise
        finally:
            con.close()
        return SCHEMA_VERSION

    def snapshot(self, *, reason='manuale', directory=None):
        """Copia coerente dell'archivio (API di backup di SQLite) con verifica di integrità."""
        directory = Path(directory) if directory else self.path.parent / 'backups'
        directory.mkdir(parents=True, exist_ok=True)
        name = 'wr_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.sqlite3'
        target = directory / name
        pending = target.with_suffix('.partial')
        source = self.connect()
        try:
            copy = sqlite3.connect(pending)
            try:
                source.backup(copy)
                if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Copia di sicurezza non valida: integrità non superata.')
            finally:
                copy.close()
            pending.replace(target)
        finally:
            source.close()
            if pending.exists():
                pending.unlink()
        return target


def _statements(script):
    """Divide uno script SQL in istruzioni complete (senza usare executescript,
    che chiuderebbe la transazione in corso)."""
    buffer = ''
    for line in script.splitlines(keepends=True):
        if line.strip().startswith('--'):
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                yield statement
            buffer = ''
    if buffer.strip():
        raise ValueError('Istruzione SQL incompleta nello schema.')

