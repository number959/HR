"""Console amministrativa: errori di input leggibili, senza traceback né account parziali."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import core
import manage


class ManageConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = core.DB
        self.data = Path(self.tmp.name) / 'data'
        self.key = Path(self.tmp.name) / 'private' / 'server.key'

    def tearDown(self):
        core.DB = self.previous
        self.tmp.cleanup()

    def run_console(self, *args, answers=(), passwords=()):
        argv = ['manage.py', *args, '--data-dir', str(self.data), '--key-file', str(self.key)]
        with patch('sys.argv', argv), patch('builtins.input', side_effect=list(answers)), \
                patch('getpass.getpass', side_effect=list(passwords)), redirect_stdout(io.StringIO()) as out:
            manage.main()
        return out.getvalue()

    def test_init_with_missing_name_explains_the_problem_and_creates_no_account(self):
        with self.assertRaises(SystemExit) as stop:
            self.run_console('init', answers=['admin', '', 'Centro di prova'],
                             passwords=['Password-di-prova-2026!'] * 2)
        self.assertIn('Operazione non completata', str(stop.exception.code))
        self.assertIn('Indicare nome', str(stop.exception.code))
        with core.connect() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM users').fetchone())
        # The same command can simply be repeated with complete data.
        output = self.run_console('init', answers=['admin', 'Amministrazione', 'Centro di prova'],
                                  passwords=['Password-di-prova-2026!'] * 2)
        self.assertIn('Codice di attivazione', output)
        with self.assertRaises(SystemExit) as again:
            self.run_console('init')
        self.assertIn('già inizializzato', str(again.exception.code))

    def test_short_temporary_password_is_refused_with_a_readable_message(self):
        self.run_console('init', answers=['admin', 'Amministrazione', 'Centro di prova'],
                         passwords=['Password-di-prova-2026!'] * 2)
        with self.assertRaises(SystemExit) as stop:
            self.run_console('reset-password', '--username', 'admin',
                             answers=['Verifica identità con documento'], passwords=['breve', 'breve'])
        self.assertIn('Password da 12 a 256 caratteri', str(stop.exception.code))


if __name__ == '__main__':
    unittest.main()
