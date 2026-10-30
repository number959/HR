"""Opzioni di avvio del servizio web e presa di ascolto condivisa fra i processi di lavoro."""
import socket
import unittest

import support  # noqa: F401  (aggiunge la cartella del motore al percorso)
from wr import months, server


class ServerOptions(unittest.TestCase):
    def test_defaults_keep_a_single_process(self):
        a = server.parser().parse_args(['--origin', 'https://wr.esempio.it'])
        self.assertEqual((a.processes, a.threads, a.port), (1, 8, 8080))

    def test_processes_option(self):
        a = server.parser().parse_args(['--origin', 'https://wr.esempio.it', '--processes', '4', '--threads', '6'])
        self.assertEqual((a.processes, a.threads), (4, 6))

    def test_bind_socket_listens_on_loopback_only(self):
        sock = server.bind_socket(0)
        try:
            host, port = sock.getsockname()
            self.assertEqual(host, '127.0.0.1')
            self.assertGreater(port, 0)
            client = socket.create_connection(('127.0.0.1', port), timeout=2)
            client.close()
        finally:
            sock.close()


class MonthBounds(unittest.TestCase):
    def test_bounds_cover_every_day_of_the_month_only(self):
        first, last = months.bounds('2026-02')
        self.assertEqual(first, '2026-02-01')
        self.assertTrue(first <= '2026-02-01' and '2026-02-28' <= last < '2026-03-01')
        self.assertFalse(first <= '2026-01-31' <= last)
        self.assertFalse(first <= '2026-03-01' <= last)


if __name__ == '__main__':
    unittest.main()
