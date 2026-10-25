import shutil
import tempfile
import unittest
from pathlib import Path

from support import PortalCase
from wr import backups


class Backups(PortalCase):
    def setUp(self):
        super().setUp()
        self.target = Path(tempfile.mkdtemp(prefix='wr-nas-'))

    def tearDown(self):
        shutil.rmtree(self.target, ignore_errors=True)
        super().tearDown()

    def test_manual_backup_list_and_download(self):
        self.portal.step_up(self.admin)
        created = self.admin.ok('POST', '/api/backups')
        listing = self.admin.ok('GET', '/api/backups')
        self.assertIn(created['filename'], [f['filename'] for f in listing['files']])
        self.portal.step_up(self.admin)
        download = self.admin.get(f'/api/backups/files/{created["filename"]}')
        self.assertTrue(download.body.startswith(b'SQLite format 3\x00'))
        self.assertStatus(self.admin.get('/api/backups/files/..%2Fwr.sqlite3'), 400)
        hr = self.portal.user('hrcentrale', 'hr')
        self.assertStatus(hr.get('/api/backups'), 403)

    def test_second_copy_disabled_by_default(self):
        status = backups.status(self.portal.db)
        self.assertFalse(status['enabled'])
        self.assertEqual(backups.run(self.portal.db)['copy_count'], 0)

    def test_second_copy_is_verified_and_probed(self):
        self.portal.step_up(self.admin)
        refused = self.admin.put('/api/backups/policy', {'enabled': True, 'destination': str(self.portal.tmp / 'data' / 'altro')})
        self.assertStatus(refused, 400)
        self.portal.step_up(self.admin)
        self.admin.ok('PUT', '/api/backups/policy', {'enabled': True, 'destination': str(self.target), 'retention_count': 2})
        for _ in range(3):
            self.portal.step_up(self.admin)
            result = self.admin.ok('POST', '/api/backups/policy/run', {'probe': True})
        self.assertTrue(result['last_probe']['ok'], result)
        managed = [p for p in self.target.iterdir() if p.name.startswith('NefroCenter-WR-backups-')]
        self.assertEqual(len(managed), 1)
        copies = [p for p in managed[0].iterdir() if p.name.startswith('copia_')]
        self.assertEqual(len(copies), 2, 'conservate solo le due copie più recenti')
        self.assertEqual(result['last_error'], '')

    def test_foreign_folder_is_not_touched(self):
        foreign = self.target / 'documenti-altrui'
        foreign.mkdir()
        (foreign / 'file.txt').write_text('non toccare')
        self.portal.step_up(self.admin)
        self.admin.ok('PUT', '/api/backups/policy', {'enabled': True, 'destination': str(self.target), 'retention_count': 1})
        self.portal.step_up(self.admin)
        self.admin.ok('POST', '/api/backups/policy/run', {})
        self.assertEqual((foreign / 'file.txt').read_text(), 'non toccare')


if __name__ == '__main__':
    unittest.main()
