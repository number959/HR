"""Serve only the synthetic demo assets. No enterprise database or credentials."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path
import argparse
import os
import re


class DemoHandler(SimpleHTTPRequestHandler):
    """Serve byte ranges for MP4 seeking, including before playback starts."""

    def send_head(self):
        self._byte_range = None
        target = Path(self.translate_path(self.path))
        self._accept_ranges = target.suffix.lower() == '.mp4' and target.is_file()
        requested = self.headers.get('Range', '')
        # HEAD has the headers of the full resource. If-Range validators are
        # deliberately not interpreted: send the full current file instead.
        if (not self._accept_ranges or self.command != 'GET'
                or not requested.startswith('bytes=') or self.headers.get('If-Range')):
            return super().send_head()
        try:
            source = target.open('rb')
        except OSError:
            return super().send_head()
        stat = os.fstat(source.fileno())
        size = stat.st_size
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested) if len(requested) < 200 else None
        start, end = 0, -1
        if match and size:
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            elif last and int(last) > 0:
                start, end = max(0, size - int(last)), size - 1
        if not (0 <= start <= end < size):
            source.close()
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return None
        self._byte_range = (start, end)
        source.seek(start)
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(str(target)))
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Last-Modified', self.date_time_string(stat.st_mtime))
        self.end_headers()
        return source

    def end_headers(self):
        if getattr(self, '_accept_ranges', False):
            self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def copyfile(self, source, outputfile):
        if self._byte_range is None:
            return super().copyfile(source, outputfile)
        start, end = self._byte_range
        remaining = end - start + 1
        while remaining:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Demo NefroCenter con dati fittizi')
    parser.add_argument('--lan',action='store_true',help='Consenti accesso dalla rete locale')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    directory=Path(__file__).resolve().parent/'dist'
    if not (directory/'index.html').is_file():raise SystemExit('Cartella dist mancante: estrarre tutto il pacchetto.')
    host='0.0.0.0' if args.lan else '127.0.0.1'
    print(f'Demo sul computer: http://localhost:{args.port}',flush=True)
    if args.lan:print(f'Dalla stessa rete: http://INDIRIZZO_IP_DI_QUESTO_PC:{args.port} (verificare il firewall).',flush=True)
    print('Solo dati fittizi. Le modifiche restano nella scheda del visitatore. Ctrl+C per arrestare.',flush=True)
    server=ThreadingHTTPServer((host,args.port),partial(DemoHandler,directory=str(directory)))
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
