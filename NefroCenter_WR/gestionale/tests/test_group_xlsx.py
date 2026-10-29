import unittest

from test_attendance import MONTH, AttendanceCase


class GroupExcel(AttendanceCase):
    """Riepilogo di gruppo in Excel: stesse regole di accesso del CSV."""

    def test_admin_downloads_group_summary_and_operator_cannot(self):
        self.entry(self.manager, day='2026-10-05')
        response = self.admin.request('GET', f'/api/overview/{MONTH}/export.xlsx')
        self.assertEqual(response.status, 200, response.body[:200])
        self.assertTrue(response.body.startswith(b'PK'))
        self.assertIn(f'riepilogo_gruppo_{MONTH}.xlsx', response.header('Content-Disposition'))
        self.assertStatus(self.operator.get(f'/api/overview/{MONTH}/export.xlsx'), 403)
        history = self.admin.ok('GET', f'/api/attendance/{self.cid}/{MONTH}')['history']
        self.assertTrue(all('riepilogo di gruppo' not in h['action'] for h in history), 'lo storico di struttura non registra esportazioni di gruppo')


if __name__ == '__main__':
    unittest.main()
