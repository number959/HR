"""Avvio del servizio web con Waitress e attività periodiche (backup, promemoria).

Il servizio ascolta solo su 127.0.0.1: in azienda va esposto tramite un reverse
proxy HTTPS. La modalità --dev-http è ammessa solo per prove su questo computer.
"""
import argparse
import logging
import os
import threading
import time
from pathlib import Path

from . import PRODUCT, VERSION, app as factory, backups, reminders

LOG = logging.getLogger('wr.server')
MAX_BODY = 20_000_000


def schedulers(application):
    db = application.db

    def hourly():
        while True:
            backups.scheduled(db)
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
                   help='Indirizzo pubblico del portale, per esempio https://wr.azienda.it')
    p.add_argument('--port', type=int, default=int(os.environ.get('WR_PORT', '8080')))
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--dev-http', action='store_true', help='Solo prove locali: http://127.0.0.1')
    return p


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    args = parser().parse_args(argv)
    if not args.origin:
        raise SystemExit('Indicare --origin con l’indirizzo del portale (per esempio https://wr.azienda.it).')
    db_path = args.data_dir / factory.DB_NAME
    if not db_path.exists():
        raise SystemExit('Archivio non trovato: per una nuova installazione usare «python manage.py init».')
    application = factory.create(args.data_dir, origin=args.origin, key_file=args.key_file, dev=args.dev_http)
    schedulers(application)
    from waitress import serve
    print(f'{PRODUCT} {VERSION} · {application.origin} (porta locale {args.port})', flush=True)
    serve(application, host='127.0.0.1', port=args.port, threads=args.threads, max_request_body_size=MAX_BODY,
          trusted_proxy='127.0.0.1', trusted_proxy_headers={'x-forwarded-for', 'x-forwarded-proto'},
          clear_untrusted_proxy_headers=True, ident=PRODUCT)


if __name__ == '__main__':
    main()
