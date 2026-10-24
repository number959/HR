"""The local demo must support chapter seeking before an MP4 has loaded."""
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from avvia_demo import DemoHandler


class QuietHandler(DemoHandler):
    def log_message(self, *args):
        pass


class DemoMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = TemporaryDirectory(prefix='nefro-demo-media-')
        cls.video = bytes(range(256)) * 800
        (Path(cls.folder.name) / 'video.mp4').write_bytes(cls.video)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=cls.folder.name))
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.folder.cleanup()

    def request(self, method='GET', headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request(method, '/video.mp4', headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_full_and_head_resource(self):
        status, headers, body = self.request()
        self.assertEqual((status, body), (200, self.video))
        self.assertEqual(headers['Accept-Ranges'], 'bytes')
        self.assertEqual(headers['Content-Length'], str(len(self.video)))
        status, headers, body = self.request('HEAD', {'Range': 'bytes=10-29'})
        self.assertEqual((status, body), (200, b''))
        self.assertEqual(headers['Content-Length'], str(len(self.video)))
        self.assertNotIn('Content-Range', headers)

    def test_closed_open_and_suffix_ranges(self):
        for requested, start, end in [('bytes=10-29', 10, 29), ('bytes=70000-', 70000, len(self.video)-1),
                                      ('bytes=-15', len(self.video)-15, len(self.video)-1)]:
            with self.subTest(requested=requested):
                status, headers, body = self.request(headers={'Range': requested})
                self.assertEqual((status, body), (206, self.video[start:end+1]))
                self.assertEqual(headers['Content-Range'], f'bytes {start}-{end}/{len(self.video)}')
                self.assertEqual(headers['Content-Length'], str(len(body)))
                self.assertEqual(headers['Accept-Ranges'], 'bytes')

    def test_unsatisfiable_and_invalid_range(self):
        for requested in ('bytes=999999999-', 'bytes=29-10', 'bytes=-0', 'bytes=-', 'bytes=0-1,4-5'):
            with self.subTest(requested=requested):
                status, headers, body = self.request(headers={'Range': requested})
                self.assertEqual((status, body), (416, b''))
                self.assertEqual(headers['Content-Range'], f'bytes */{len(self.video)}')

    def test_if_range_sends_full_resource(self):
        status, headers, body = self.request(headers={'Range': 'bytes=10-29', 'If-Range': 'unknown-validator'})
        self.assertEqual((status, body), (200, self.video))
        self.assertNotIn('Content-Range', headers)


if __name__ == '__main__':
    unittest.main()
