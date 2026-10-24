"""Document review decisions, central visibility, scope and immutable history."""
import base64
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
import threading

import core
import document_reviews as reviews
import hr
import test_structures as fixtures


class DocumentReviewTests(unittest.TestCase):
    tearDown = fixtures.StructureTests.tearDown
    user = fixtures.StructureTests.user

    def setUp(self):
        fixtures.StructureTests.setUp(self)
        reviews.init(core)
        self.pid = self.person(self.one)
        self.doc = self.upload()

    def person(self, cid):
        with core.connect() as c:
            revision = core.center(c, cid)['revision']
        return hr.save(core, self.admin, dict(cid=cid, revision=revision, version=0,
            name='Persona documento', role='INF', registration='DOC1', fields={}, custom={}))['pid']

    def upload(self, **fields):
        return hr.document_add(core, self.manager, dict(cid=self.one, pid=self.pid,
            name='contratto.pdf', category='Contratto', expiry=fields.get('expiry', '2090-01-01'),
            content=base64.b64encode(b'%PDF-1.4\nDocumento di prova\n%%EOF').decode()))['id']

    def update(self, status, version=1, user=None, **fields):
        return reviews.review(core, user or self.hr, dict(cid=self.one, id=self.doc,
            version=version, status=status, note='Verifica documentale effettuata', **fields))

    def test_upload_received_and_immediately_visible_to_central_hr(self):
        detail = reviews.read(core, self.hr, self.one, self.doc)
        self.assertEqual((detail['review']['status'], detail['review']['version']), ('received', 1))
        self.assertEqual(len(detail['history']), 1)
        self.assertTrue(detail['can_review'])
        index = hr.document_index(core, self.hr, review='received')
        self.assertEqual([self.doc], [d['id'] for d in index['documents']])
        self.assertEqual(hr.read(core, self.manager, self.one, self.pid)['documents'][0]['review'], detail['review'])

    def test_correction_resubmission_and_final_decision_permissions(self):
        with self.assertRaises(PermissionError):
            self.update('verified', user=self.manager)
        with self.assertRaises(ValueError):
            reviews.review(core, self.hr, dict(cid=self.one, id=self.doc, version=1,
                                              status='needs_correction', note='breve'))
        self.update('needs_correction')
        detail = reviews.read(core, self.manager, self.one, self.doc)
        self.assertTrue(detail['can_resubmit']); self.assertFalse(detail['can_review'])
        self.update('received', 2, self.manager)
        with self.assertRaises(ValueError):
            self.update('received', 3, self.manager)
        final = self.update('verified', 3)
        self.assertEqual([r['status'] for r in final['history']],
                         ['verified', 'received', 'needs_correction', 'received'])
        self.assertEqual(len(hr.document_index(core, self.hr, review='verified')['documents']), 1)
        self.assertEqual(hr.document_index(core, self.hr, review='needs_correction')['total'], 0)

    def test_scope_and_revocation_are_checked_on_reads_and_writes(self):
        for user in (self.operator, self.viewer):
            with self.assertRaises(PermissionError): reviews.read(core, user, self.one, self.doc)
            with self.assertRaises(PermissionError): self.update('verified', user=user)
        with self.assertRaises(PermissionError): reviews.read(core, self.manager, self.two, self.doc)
        with self.assertRaises(ValueError): reviews.read(core, self.hr, self.two, self.doc)
        with core.connect() as c:
            c.execute('UPDATE users SET centers=? WHERE id=?', (core.dump([self.two]), self.manager['id']))
            c.execute("UPDATE users SET role='viewer',centers=? WHERE id=?", (core.dump([self.one]), self.hr['id']))
            c.commit()
        with self.assertRaises(PermissionError): reviews.read(core, self.manager, self.one, self.doc)
        with self.assertRaises(PermissionError): self.update('verified')
        with core.connect() as c:
            c.execute('UPDATE users SET active=0 WHERE id=?', (self.admin['id'],)); c.commit()
        with self.assertRaises(core.AuthenticationError): self.update('verified', user=self.admin)

    def test_expiry_is_derived_without_rewriting_recorded_verification(self):
        self.update('verified')
        with core.connect() as c:
            document = dict(c.execute('SELECT * FROM hr_documents WHERE id=?', (self.doc,)).fetchone())
            later = reviews.metadata(c, document, today='2091-01-01')
            self.assertEqual((later['status'], later['effective_status'], later['version']), ('verified', 'expired', 2))
            self.assertEqual(c.execute('SELECT count(*) FROM hr_document_review_history').fetchone()[0], 2)
        expired = self.upload(expiry='2020-01-01')
        with self.assertRaisesRegex(ValueError, 'scaduto'):
            reviews.review(core, self.hr, dict(cid=self.one, id=expired, version=1, status='verified'))
        self.assertEqual([expired], [d['id'] for d in hr.document_index(core, self.hr, review='expired')['documents']])

    def test_legacy_files_never_become_verified_during_migration(self):
        with core.connect() as c:
            c.execute('DELETE FROM hr_document_review_history WHERE document_id=?', (self.doc,))
            c.execute('DELETE FROM hr_document_reviews WHERE document_id=?', (self.doc,)); c.commit()
        reviews.init(core)
        detail = reviews.read(core, self.hr, self.one, self.doc)
        self.assertTrue(detail['legacy_unreviewed'])
        self.assertEqual((detail['review']['version'], detail['review']['status'], detail['history']), (0, 'received', []))
        self.assertEqual(self.update('verified', 0)['review']['version'], 1)

    def test_history_paging_and_invalid_inputs(self):
        self.update('needs_correction'); self.update('received', 2, self.manager)
        page = reviews.read(core, self.hr, self.one, self.doc, offset='1', limit='1')
        self.assertEqual((page['history_total'], page['history'][0]['version']), (3, 2))
        for offset, limit in ((True, 25), (0, False), (0, 101), (-1, 25), ('1.5', 25), (1000001, 1)):
            with self.subTest(offset=offset, limit=limit), self.assertRaises(ValueError):
                reviews.read(core, self.hr, self.one, self.doc, offset, limit)
        for version in (True, '3', 1, None):
            with self.subTest(version=version), self.assertRaises(ValueError): self.update('verified', version)
        for body in ([], None, {'cid': [], 'id': self.doc}):
            with self.assertRaises(ValueError): reviews.review(core, self.hr, body)
        with self.assertRaises(ValueError): hr.document_index(core, self.hr, review='other')

    def test_simultaneous_decisions_keep_one_confirmed_history_entry(self):
        ready = threading.Barrier(2)
        def decide(status):
            ready.wait(timeout=5)
            try: return self.update(status)
            except ValueError: return None
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(decide, ['verified', 'needs_correction']))
        self.assertEqual(sum(r is not None for r in results), 1)
        detail = reviews.read(core, self.hr, self.one, self.doc)
        self.assertEqual((detail['review']['version'], detail['history_total']), (2, 2))

    def test_deletion_hides_history_but_keeps_audit_decision(self):
        self.update('verified')
        hr.document_delete(core, self.hr, dict(cid=self.one, id=self.doc, reason='Rimozione di prova'))
        with self.assertRaises(ValueError): reviews.read(core, self.hr, self.one, self.doc)
        with core.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM hr_document_review_history').fetchone()[0], 0)
            event = c.execute("SELECT after_data FROM audit WHERE action='Verifica documento HR aggiornata'").fetchone()
            self.assertEqual(json.loads(event[0])['document_id'], self.doc)


if __name__ == '__main__': unittest.main()
