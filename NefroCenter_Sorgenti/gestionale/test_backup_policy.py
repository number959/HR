"""Verified NAS copies: real SQLite snapshots, document hashes and conservative retention."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backup_policy
import core
import hr
from test_analytics import StatisticsFixture


class BackupPolicyTests(StatisticsFixture):
    def setUp(self):
        super().setUp()
        self.nas_tmp=tempfile.TemporaryDirectory()
        self.nas=Path(self.nas_tmp.name)
        hr.save(core,self.admin,{**self.req(), 'pid':self.person,'version':0,
            'name':'Persona demo','registration':'M001','role':'INF','active':True,
            'stage':'active','fields':{},'custom':{}})

    def tearDown(self):
        self.nas_tmp.cleanup()
        super().tearDown()

    def enable(self, retention=0):
        return backup_policy.configure(core,dict(enabled=True,destination=str(self.nas),
            retention_count=retention,probe_interval_days=30),self.admin)

    def copies(self):
        return list(self.nas.glob('NefroCenter-backups-*/copia_*'))

    def test_default_is_disabled_and_configuration_scope_is_fresh(self):
        self.assertFalse(backup_policy.status(core,self.admin)['enabled'])
        with patch.object(backup_policy,'_copy_file') as copied:
            backup_policy.run(core)
            copied.assert_not_called()
        for user in (self.operator,self.viewer):
            with self.assertRaises(PermissionError):backup_policy.status(core,user)
            with self.assertRaises(PermissionError):backup_policy.configure(core,{},user)
            with self.assertRaises(PermissionError):backup_policy.run_admin(core,user)
        with core.connect() as c:
            c.execute('UPDATE users SET role=? WHERE id=?',('viewer',self.admin['id']));c.commit()
        with self.assertRaises(PermissionError):backup_policy.status(core,self.admin)

    def test_destination_must_be_separate_mounted_and_without_symlinks(self):
        for destination in (str(self.nas/'missing'),str(core.DB.parent),str(core.DB.parent/'backups'),str(core.DB.parent.parent),'relative'):
            with self.subTest(destination=destination),self.assertRaises(ValueError):
                backup_policy.configure(core,dict(enabled=True,destination=destination),self.admin)
        alias=self.nas/'alias';alias.symlink_to(core.DB.parent,target_is_directory=True)
        with self.assertRaises(ValueError):backup_policy.configure(core,dict(enabled=True,destination=str(alias)),self.admin)
        # A future mount can be saved disabled, without causing any copy.
        result=backup_policy.configure(core,dict(enabled=False,destination=str(self.nas/'future')))
        self.assertIn('destination_error',result)

    def test_document_snapshot_and_isolated_restore_probe_do_not_touch_live_database(self):
        payload=b'%PDF-1.4\nDocumento personale dimostrativo\n%%EOF'
        hr.document_add(core,self.admin,dict(cid=self.a,pid=self.person,name='contratto.pdf',
            category='Contratto',content=base64.b64encode(payload).decode()))
        self.enable()
        result=backup_policy.run_admin(core,self.admin,probe=True)
        self.assertEqual(result['copy_count'],1)
        self.assertTrue(result['last_probe']['ok'])
        self.assertEqual(result['last_probe']['documents_bytes'],len(payload))
        self.assertEqual(result['last_probe']['rows']['hr_documents'],1)
        copied=self.copies()[0]/'presenze.sqlite3'
        self.assertEqual(backup_policy._digest(copied),result['last_copy']['sha256'])
        self.assertEqual(hr.read(core,self.admin,self.a,self.person)['documents'][0]['name'],'contratto.pdf')
        self.assertFalse(list(core.DB.parent.glob('.backup-prova-*')))
        with patch.object(backup_policy,'_copy_file') as copy_file:
            backup_policy.run(core)
            copy_file.assert_not_called()

    def test_corrupt_attachment_in_completed_source_is_rejected_without_publication(self):
        hr.document_add(core,self.admin,dict(cid=self.a,pid=self.person,name='contratto.pdf',
            category='Contratto',content=base64.b64encode(b'%PDF-1.4\n%%EOF').decode()))
        with core.connect() as c:
            c.execute('UPDATE hr_documents SET content=?',(b'alterato',));c.commit()
        core._backup();self.enable()
        with self.assertRaisesRegex(ValueError,'allegato HR'):backup_policy.run(core,force=True)
        self.assertEqual(self.copies(),[])
        self.assertIn('allegato HR',backup_policy.status(core,self.admin)['last_error'])

    def test_failed_copy_preserves_previous_verified_copy_and_cleans_staging(self):
        self.enable(retention=1)
        core._backup();backup_policy.run(core,force=True)
        first=self.copies()[0]
        original=backup_policy._copy_file
        def corrupted(source,target):
            original(source,target)
            with target.open('ab') as dest:dest.write(b'alterato')
        with patch.object(backup_policy,'_copy_file',side_effect=corrupted):
            with self.assertRaisesRegex(ValueError,'non corrisponde'):backup_policy.run(core,force=True)
        self.assertEqual(self.copies(),[first])
        self.assertFalse(list(self.nas.glob('NefroCenter-backups-*/.pending-*')))
        self.assertTrue(backup_policy.status(core,self.admin)['last_error'])

    def test_retention_only_deletes_owned_verified_copies_after_success(self):
        self.enable(retention=1);core._backup()
        originals=set((core.DB.parent/'backups').iterdir())
        backup_policy.run(core,force=True);first=self.copies()[0]
        unknown=first.parent/'archivio-personale';unknown.mkdir();(unknown/'nota.txt').write_text('conservare')
        result=backup_policy.run(core,force=True)
        self.assertEqual(len(self.copies()),1);self.assertFalse(first.exists())
        self.assertEqual(result['copy_count'],1)
        self.assertTrue((unknown/'nota.txt').is_file())
        self.assertEqual(originals,set((core.DB.parent/'backups').iterdir()))
        first=self.copies()[0]
        (first/'documento-aggiunto.txt').write_text('non cancellare')
        result=backup_policy.run(core,force=True)
        self.assertTrue(result['retention_error']);self.assertEqual(len(self.copies()),2)
        self.assertTrue((first/'documento-aggiunto.txt').is_file())

    def test_missing_nas_reports_error_then_success_clears_it(self):
        self.enable();core._backup()
        self.nas.rmdir()
        with self.assertRaises(ValueError):backup_policy.run(core,force=True)
        self.assertTrue(backup_policy.status(core,self.admin)['last_error'])
        self.nas.mkdir()
        result=backup_policy.run(core,force=True)
        self.assertEqual(result['last_error'],'');self.assertIsNotNone(result['last_success'])


if __name__ == '__main__':unittest.main()
