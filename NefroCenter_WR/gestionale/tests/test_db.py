import sqlite3
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  (percorso del pacchetto)
from wr import SCHEMA_VERSION
from wr.db import Database, LegacyArchive


class Archive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'wr.sqlite3'

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_archive_and_idempotent_migration(self):
        db = Database(self.path)
        self.assertEqual(db.migrate(), SCHEMA_VERSION)
        self.assertEqual(db.migrate(), SCHEMA_VERSION)
        self.assertEqual(db.schema_version(), SCHEMA_VERSION)
        with db.read() as con:
            self.assertEqual(con.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(con.execute('PRAGMA foreign_keys').fetchone()[0], 1)

    def test_wal_size_limit_and_hourly_maintenance(self):
        db = Database(self.path)
        db.migrate()
        with db.write() as con:
            con.execute("INSERT INTO meta(key,value) VALUES('prova','x')")
        with db.read() as con:
            self.assertEqual(con.execute('PRAGMA journal_size_limit').fetchone()[0], 64 * 1024 * 1024)
        result = db.maintenance()
        self.assertFalse(result['busy'])
        self.assertEqual(result['pages'], result['moved'])
        wal = self.path.with_name(self.path.name + '-wal')
        self.assertTrue(not wal.exists() or wal.stat().st_size == 0)

    def test_legacy_archive_is_never_modified(self):
        con = sqlite3.connect(self.path)
        con.executescript('CREATE TABLE periods(cid TEXT, month TEXT, data TEXT); PRAGMA user_version=8;')
        con.close()
        before = self.path.read_bytes()
        with self.assertRaises(LegacyArchive):
            Database(self.path).migrate()
        self.assertEqual(self.path.read_bytes(), before)

    def test_newer_schema_refused(self):
        con = sqlite3.connect(self.path)
        con.execute(f'PRAGMA user_version={SCHEMA_VERSION + 1}')
        con.close()
        with self.assertRaises(RuntimeError):
            Database(self.path).migrate()

    def test_write_is_atomic_and_snapshot_is_checked(self):
        db = Database(self.path)
        db.migrate()
        with self.assertRaises(ZeroDivisionError):
            with db.write() as con:
                con.execute("INSERT INTO meta(key,value) VALUES('prova','1')")
                1 / 0
        with db.read() as con:
            self.assertIsNone(con.execute("SELECT value FROM meta WHERE key='prova'").fetchone())
        copy = db.snapshot(reason='prova', directory=Path(self.tmp.name) / 'copie')
        self.assertTrue(copy.name.startswith('wr_') and copy.suffix == '.sqlite3')
        check = sqlite3.connect(copy)
        self.assertEqual(check.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
        check.close()


if __name__ == '__main__':
    unittest.main()
