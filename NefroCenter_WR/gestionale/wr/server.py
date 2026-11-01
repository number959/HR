"""Avvio del servizio web con Waitress e attività periodiche (backup, promemoria).

Il servizio ascolta solo su 127.0.0.1: in azienda va esposto tramite un reverse
proxy HTTPS. La modalità --dev-http è ammessa solo per prove su questo computer.

Processi di lavoro (--processes): Python esegue un solo thread per volta in ogni processo,
quindi con molti utenti contemporanei un processo unico rallenta anche se il database è veloce.
Con --processes N il processo principale apre la porta, avvia N processi che servono le richieste
dalla stessa presa e tiene per sé le attività periodiche. SQLite in modalità WAL ammette più
processi sullo stesso archivio (su disco locale). Dove manca os.fork (Windows) resta un processo.
"""
import argparse
import logging
import os
import signal
import socket
import threading
import time
from pathlib import Path

from . import PRODUCT, VERSION, app as factory, backups, reminders

LOG = logging.getLogger('wr.server')
MAX_BODY = 20_000_000
MAX_RESTARTS_PER_MINUTE = 10


def schedulers(application):
    db = application.db

    def hourly():
        while True:
            backups.scheduled(db)
            try:
                db.maintenance()
            except Exception:
                LOG.exception('Manutenzione dell’archivio non riuscita')
            time.sleep(3600)

    def every_five_minutes():
        while True:
            try:
                reminders.run(db, transport=application.services.get('mail_transport'))
            except Exception:
                LOG.exception('Promemoria automatici non riusciti')
            time.sleep(300)

    threading.Thread(target=hourly, daemon=True, name='backup').start()
    threading.Thread(target=every_five_minutes, daemon=True, name='promemoria').start()


def parser():
    p = argparse.ArgumentParser(description=f'{PRODUCT} {VERSION} · servizio web')
    p.add_argument('--data-dir', type=Path, default=Path(os.environ.get('WR_DATA_DIR', 'data')))
    p.add_argument('--key-file', type=Path, default=Path(os.environ.get('WR_KEY_FILE', 'private/server.key')))
    p.add_argument('--origin', default=os.environ.get('WR_ORIGIN', ''),
                   help='Indirizzo pubblico del portale, per esempio https://wr.esempio.it')
    p.add_argument('--port', type=int, default=int(os.environ.get('WR_PORT', '8080')))
    p.add_argument('--threads', type=int, default=8, help='Thread per processo (predefinito 8)')
    p.add_argument('--processes', type=int, default=int(os.environ.get('WR_PROCESSES', '1')),
                   help='Processi di lavoro (predefinito 1; consigliati 2-4 su un server con più CPU e molti utenti)')
    p.add_argument('--dev-http', action='store_true', help='Solo prove locali: http://127.0.0.1')
    return p


def workers_supported():
    return hasattr(os, 'fork')


def bind_socket(port, host='127.0.0.1', backlog=1024):
    """Apre la porta nel processo principale: i processi di lavoro accettano dalla stessa presa."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(backlog)
    return sock


def serve_forever(application, args, sock=None):
    from waitress import serve
    options = dict(threads=args.threads, max_request_body_size=MAX_BODY, trusted_proxy='127.0.0.1',
                   trusted_proxy_headers={'x-forwarded-for', 'x-forwarded-proto'}, clear_untrusted_proxy_headers=True,
                   ident=PRODUCT)
    if sock is None:
        serve(application, host='127.0.0.1', port=args.port, **options)
    else:
        serve(application, sockets=[sock], **options)


def run_workers(application, args):
    """Processo principale: tiene la porta, sorveglia i processi di lavoro e fa girare le attività periodiche."""
    sock = bind_socket(args.port)
    children = {}
    restarts = []
    stopping = False

    def spawn(index):
        pid = os.fork()
        if pid == 0:  # processo di lavoro
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            try:
                serve_forever(application, args, sock)
            finally:
                os._exit(0)
        children[pid] = index

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        for pid in list(children):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    for index in range(args.processes):
        spawn(index)
    schedulers(application)  # solo qui, dopo i fork: nessun thread attraversa la duplicazione del processo
    while children:
        try:
            pid, status = os.wait()
        except ChildProcessError:
            break
        except InterruptedError:
            continue
        index = children.pop(pid, None)
        if index is None or stopping:
            continue
        now = time.monotonic()
        restarts[:] = [t for t in restarts if now - t < 60] + [now]
        if len(restarts) > MAX_RESTARTS_PER_MINUTE:
            stop(None, None)
            raise SystemExit('I processi di lavoro terminano in continuazione: servizio fermato, controllare il registro.')
        LOG.warning('Processo di lavoro %s terminato (stato %s): lo riavvio.', index + 1, status)
        time.sleep(1)
        spawn(index)
    sock.close()


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    args = parser().parse_args(argv)
    if not args.origin:
        raise SystemExit('Indicare --origin con l’indirizzo del portale (per esempio https://wr.esempio.it).')
    db_path = args.data_dir / factory.DB_NAME
    if not db_path.exists():
        raise SystemExit('Archivio non trovato: per una nuova installazione usare «python manage.py init».')
    if args.processes < 1 or args.threads < 1:
        raise SystemExit('--processes e --threads devono essere almeno 1.')
    if args.processes > 1 and not workers_supported():
        LOG.warning('Più processi di lavoro non sono disponibili su questo sistema: uso un processo solo.')
        args.processes = 1
    application = factory.create(args.data_dir, origin=args.origin, key_file=args.key_file, dev=args.dev_http)
    print(f'{PRODUCT} {VERSION} · {application.origin} (porta locale {args.port}, processi {args.processes}, '
          f'thread per processo {args.threads})', flush=True)
    if args.processes > 1:
        run_workers(application, args)
    else:
        schedulers(application)
        serve_forever(application, args)


if __name__ == '__main__':
    main()
