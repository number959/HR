import io
import unittest
import zipfile

from test_attendance import MONTH, AttendanceCase


class Statistics(AttendanceCase):
    def setUp(self):
        super().setUp()
        self.entry(self.operator)
        self.entry(self.operator, day='2026-10-06', code='FE')
        self.entry(self.manager, day='2026-10-07', start='', end='')

    def test_report_totals_and_filters(self):
        data = self.manager.ok('GET', f'/api/statistics?from={MONTH}&to={MONTH}&cid={self.cid}')
        self.assertEqual(data['summary']['work_shifts'], 2)
        self.assertEqual(data['summary']['missing_hours'], 1)
        self.assertEqual(data['summary']['absence_slots'], 1)
        self.assertEqual(data['summary']['hours_completeness'], 50.0)
        self.assertEqual([c['code'] for c in data['by_cause']], ['FE'])
        self.assertIsNotNone(data['hr'])
        filtered = self.manager.ok('GET', f'/api/statistics?from={MONTH}&to={MONTH}&cid={self.cid}&role=MED')
        self.assertEqual(filtered['summary']['work_shifts'], 0)
        self.assertStatus(self.manager.get(f'/api/statistics?from=2026-01&to=2028-01'), 400, '24 mesi')
        self.assertStatus(self.manager.get(f'/api/statistics?from={MONTH}&to={MONTH}&person_id={self.anna}'), 400)

    def test_viewer_has_no_hr_block_and_csv_follows_flag(self):
        viewer = self.portal.user('direzione', 'viewer', [self.cid])
        data = viewer.ok('GET', f'/api/statistics?from={MONTH}&to={MONTH}')
        self.assertIsNone(data['hr'])
        self.assertTrue(data['export_allowed'])
        self.assertEqual(viewer.get(f'/api/statistics/export.csv?from={MONTH}&to={MONTH}').status, 200)
        self.assertEqual(self.save_config(lambda c: c.update(operator_export=False)).status, 200)
        self.assertStatus(viewer.get(f'/api/statistics/export.csv?from={MONTH}&to={MONTH}'), 403)

    def test_excel_exports(self):
        grid = self.manager.get(f'/api/exports/xlsx?kind=presenze_centro&from={MONTH}&to={MONTH}&cid={self.cid}')
        self.assertEqual(grid.status, 200, grid.body[:300])
        names = zipfile.ZipFile(io.BytesIO(grid.body)).namelist()
        self.assertIn('xl/workbook.xml', names)
        self.assertNotIn('xl/vbaProject.bin', names)
        self.assertEqual(self.manager.get(f'/api/exports/xlsx?kind=statistiche&from={MONTH}&to={MONTH}').status, 200)
        self.portal.clock.advance(400)
        private = self.manager.get(f'/api/exports/xlsx?kind=dipendenti&from={MONTH}&to={MONTH}&cid={self.cid}')
        self.assertStatus(private, 428)
        self.portal.step_up(self.manager)
        for kind in ('dipendenti', 'onboarding', 'accordi'):
            response = self.manager.get(f'/api/exports/xlsx?kind={kind}&from={MONTH}&to={MONTH}&cid={self.cid}')
            self.assertEqual(response.status, 200, (kind, response.body[:300]))
        self.assertStatus(self.operator.get(f'/api/exports/xlsx?kind=dipendenti&from={MONTH}&to={MONTH}&cid={self.cid}'), 403)


class Overview(AttendanceCase):
    def test_group_summary_and_csv_permissions(self):
        self.entry(self.operator)
        data = self.manager.ok('GET', f'/api/overview/{MONTH}')
        row = data['centers'][0]
        self.assertEqual((row['shifts'], row['people']), (1, 2))
        self.assertStatus(self.manager.get(f'/api/overview/{MONTH}/export.csv'), 403)
        viewer = self.portal.user('direzione', 'viewer', [self.cid])
        self.assertEqual(viewer.get(f'/api/overview/{MONTH}/export.csv').status, 200)

    def test_todo_by_role(self):
        self.entry(self.manager, day='2026-10-07', start='', end='')
        self.entry(self.manager, day='2026-10-01', layer='planned')
        manager = self.manager.ok('GET', f'/api/todo/{MONTH}')
        categories = set(manager['counts'])
        self.assertTrue({'orari', 'consuntivi', 'calendario'} <= categories, categories)
        self.assertIn('fascicoli', categories)
        operator = self.operator.ok('GET', f'/api/todo/{MONTH}')
        self.assertNotIn('fascicoli', operator['counts'])
        self.assertNotIn('calendario', operator['counts'])


if __name__ == '__main__':
    unittest.main()
