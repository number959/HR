"""Console di amministrazione di NefroCenter WR (da eseguire sul server).

Comandi principali:
  init            nuova installazione: archivio, chiave, primo amministratore e prima struttura
  serve           avvia il servizio web (vedere anche wr/server.py)
  activate        nuovo codice di attivazione per un account (accesso perso o telefono cambiato)
  check           controllo in sola lettura dell'archivio
  backup          crea subito un backup locale verificato
  backup-config   configura la seconda copia (file JSON con enabled, destination, retention_count, probe_interval_days)
  backup-status   stato della seconda copia
  backup-sync     backup locale + seconda copia
  backup-probe    come backup-sync, con prova di ripristino
  after-restore   da usare DOPO aver ripristinato un backup: revoca sessioni e disattiva posta e promemoria
  migra-011       crea un nuovo archivio WR a partire da un archivio della versione 0.11 (che resta invariato)
  demo-data       crea un archivio di prova con dati fittizi (solo sviluppo, mai sui dati aziendali)

Nessun comando cancella dati. «init» rifiuta un archivio già esistente.
"""
import argparse
import getpass
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from wr import PRODUCT, VERSION  # noqa: E402
from wr.errors import WRError  # noqa: E402

def console_user():
    from wr.permissions import User
    return User(id='', username='console', name='Console del server', role='admin')


def ask(prompt, value=None):
    return value if value is not None else input(prompt).strip()


def confirm(question):
    if input(question + ' Scrivere CONFERMO per procedere: ').strip() != 'CONFERMO':
        raise SystemExit('Nessuna modifica.')


def database(data_dir):
    from wr import app
    return app.database(data_dir)


def cmd_init(a):
    from wr import app, users
    from wr.auth import Auth
    db = database(a.data_dir)
    if db.path.exists():
        if db.is_legacy():
            raise SystemExit('Nella cartella c’è un archivio della versione 0.11: usare «migra-011», non «init».')
        with closing(sqlite3.connect(f'file:{db.path.as_posix()}?mode=ro', uri=True)) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'users' in tables and con.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                raise SystemExit('Archivio già inizializzato: non viene modificato.')
    if not a.key_file.exists():
        Auth.create_key(a.key_file)
    application = app.create(a.data_dir, origin='http://127.0.0.1', key_file=a.key_file, dev=True)
    db = application.db
    username = ask('Nome utente dell’amministratore: ', a.username)
    name = ask('Nome e cognome del referente: ', a.name)
    center_name = ask('Nome della prima struttura: ', a.center_name)
    center_code = ask('Codice della prima struttura (es. CENTRO-1): ', a.center_code).upper()
    code = users.create_first_admin(db, application.auth, username, name)
    _first_center(db, center_name, center_code)
    from wr import backups
    backups.create(db, 'installazione')
    print('\nInstallazione creata.')
    print(f'Codice di attivazione per «{username}», valido {application.auth.ACTIVATION_DAYS} giorni (conservarlo con riservatezza):')
    print(f'\n    {code}\n')
    print('Al primo accesso scegliere «Primo accesso», inserire nome utente e codice, poi impostare la password personale')
    print('e l’app Authenticator. Conservare una copia protetta della chiave del server:', a.key_file)


def _first_center(db, name, code):
    from wr import audit, centers, rules
    from wr.util import dumps, new_id, stamp
    from wr import validate as v
    name = v.text(name, 'Nome della struttura', 150, required=True)
    if not centers.CODE.fullmatch(code):
        raise SystemExit('Codice struttura: da 2 a 30 lettere maiuscole, numeri, trattino o trattino basso.')
    with db.write() as con:
        cid = new_id()
        con.execute('INSERT INTO centers(id,name,code,active,config_version,version,created_at) VALUES(?,?,?,1,1,1,?)',
                    (cid, name, code, stamp()))
        con.execute('INSERT INTO center_configs(center_id,version,data,note,created_at,created_by) VALUES(?,1,?,?,?,?)',
                    (cid, dumps(rules.defaults()), 'Parametri iniziali da verificare', stamp(), 'console'))
        audit.record(con, console_user(), 'Prima struttura creata', cid, entity='center', entity_id=cid, after=dict(name=name, code=code))


def open_app(a):
    from wr import app
    db = database(a.data_dir)
    if not db.path.exists():
        raise SystemExit('Archivio non trovato: verificare --data-dir.')
    return app.create(a.data_dir, origin='http://127.0.0.1', key_file=a.key_file, dev=True)


def cmd_activate(a):
    application = open_app(a)
    if not a.username:
        raise SystemExit('Indicare --username.')
    with application.db.read() as con:
        row = con.execute('SELECT id, username FROM users WHERE username=?', (a.username.strip().casefold(),)).fetchone()
    if not row:
        raise SystemExit('Account non trovato.')
    reason = input('Motivo e riferimento della verifica d’identità (almeno 8 caratteri): ').strip()
    if len(reason) < 8:
        raise SystemExit('Motivazione troppo breve: nessuna modifica.')
    confirm(f'Il secondo fattore, i codici di recupero e le sessioni di {row["username"]} verranno revocati.')
    with application.db.write() as con:
        code = application.auth.issue_activation(con, row['id'], console_user(), reason)
    print(f'Nuovo codice di attivazione, valido {application.auth.ACTIVATION_DAYS} giorni:\n\n    {code}\n')
    print('Al primo accesso la persona sceglie una nuova password e configura di nuovo l’app Authenticator.')


def cmd_check(a):
    from wr import backups
    db = database(a.data_dir)
    if not db.path.exists():
        raise SystemExit('Archivio non trovato: verificare --data-dir.')
    if db.is_legacy():
        print(json.dumps(dict(archivio='versione 0.11', nota='usare «migra-011» per creare un archivio WR'), ensure_ascii=False))
        return
    with closing(sqlite3.connect(f'file:{db.path.as_posix()}?mode=ro', uri=True)) as con:
        result = dict(
            prodotto=PRODUCT, programma=VERSION, schema=con.execute('PRAGMA user_version').fetchone()[0],
            integrita=con.execute('PRAGMA integrity_check').fetchone()[0],
            relazioni='ok' if con.execute('PRAGMA foreign_key_check').fetchone() is None else 'da verificare',
            conteggi={t: con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                      for t in ('users', 'centers', 'people', 'entries', 'documents', 'audit')})
    result['backup'] = backups.status(db)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_backup(a):
    from wr import backups
    open_app(a)
    print(backups.create(database(a.data_dir), 'console').name)


def cmd_backup_policy(a):
    from wr import backups
    application = open_app(a)
    db = application.db
    if a.command == 'backup-config':
        if not a.policy_file:
            raise SystemExit('Indicare --policy-file con la configurazione JSON.')
        result = backups.configure(db, json.loads(a.policy_file.read_text(encoding='utf-8')))
    elif a.command == 'backup-status':
        result = backups.status(db)
    else:
        backups.create(db, 'console')
        result = backups.run(db, force=True, probe=a.command == 'backup-probe')
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_after_restore(a):
    from wr import audit, mail, reminders
    from wr.util import dumps
    application = open_app(a)
    confirm('Dopo un ripristino: revocare tutte le sessioni e i codici di recupero, disattivare posta e promemoria e '
            'sospendere gli invii in corso (operazione non in sola lettura).')
    with application.db.write() as con:
        con.execute('DELETE FROM sessions')
        con.execute("UPDATE user_security SET recovery='[]', activation_hash='', activation_until=0, generation=generation+1")
        cfg = mail.settings(con)
        if cfg['version']:
            data = {k: cfg[k] for k in mail.DEFAULT_SETTINGS}
            data['enabled'] = False
            con.execute('UPDATE mail_settings SET data=?, version=version+1 WHERE id=1', (dumps(data),))
        reason = 'Archivio ripristinato: verificare gli invii presso il server di posta prima di nuove comunicazioni.'
        for r in con.execute("SELECT id FROM mail_recipients WHERE status IN ('pending','sending')").fetchall():
            mail.mark_uncertain(con, r['id'], reason)
        reminders.after_restore(con)
        application.auth.event(con, None, 'console', 'Sessioni e recuperi revocati dopo ripristino')
        audit.record(con, console_user(), 'Operazioni dopo il ripristino', entity='restore')
    print('Sessioni e codici di recupero revocati; posta e promemoria disattivati; invii sospesi con esito incerto.')
    print('Gli utenti accedono con password e Authenticator e rigenerano i codici di recupero.')


def cmd_migrate(a):
    from wr import migrate011
    from wr.auth import Auth
    if not a.source:
        raise SystemExit('Indicare --source con il file presenze.sqlite3 della versione 0.11 (una copia di backup).')
    if not a.key_file.exists():
        Auth.create_key(a.key_file)
    report = migrate011.run(a.source, a.data_dir, a.key_file, legacy_key=a.legacy_key)
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
    if report['activation_codes']:
        print('\nCodici di attivazione (validi 7 giorni) da consegnare di persona:')
        for username, code in report['activation_codes']:
            print(f'  {username}: {code}')


def cmd_demo_data(a):
    from wr import sample
    sample.build(a.data_dir, a.key_file)
    print('Archivio di prova creato con dati fittizi in', a.data_dir)


def cmd_serve(a):
    from wr import server
    args = ['--data-dir', str(a.data_dir), '--key-file', str(a.key_file), '--origin', a.origin or '', '--port', str(a.port)]
    if a.dev_http:
        args.append('--dev-http')
    server.main(args)


COMMANDS = {'init': cmd_init, 'activate': cmd_activate, 'reset-password': cmd_activate, 'check': cmd_check,
            'backup': cmd_backup, 'backup-config': cmd_backup_policy, 'backup-status': cmd_backup_policy,
            'backup-sync': cmd_backup_policy, 'backup-probe': cmd_backup_policy, 'after-restore': cmd_after_restore,
            'migra-011': cmd_migrate, 'demo-data': cmd_demo_data, 'serve': cmd_serve}


def main(argv=None):
    p = argparse.ArgumentParser(description=f'{PRODUCT} {VERSION} · console di amministrazione')
    p.add_argument('command', choices=list(COMMANDS))
    p.add_argument('--data-dir', type=Path, default=Path(os.environ.get('WR_DATA_DIR', 'data')))
    p.add_argument('--key-file', type=Path, default=Path(os.environ.get('WR_KEY_FILE', 'private/server.key')))
    p.add_argument('--username')
    p.add_argument('--name')
    p.add_argument('--center-name')
    p.add_argument('--center-code')
    p.add_argument('--policy-file', type=Path)
    p.add_argument('--source', type=Path, help='Archivio della versione 0.11 da cui migrare (non viene modificato)')
    p.add_argument('--legacy-key', type=Path, help='Chiave del server della versione 0.11, per conservare le app Authenticator')
    p.add_argument('--origin', default=os.environ.get('WR_ORIGIN', ''))
    p.add_argument('--port', type=int, default=int(os.environ.get('WR_PORT', '8080')))
    p.add_argument('--dev-http', action='store_true')
    a = p.parse_args(argv)
    try:
        COMMANDS[a.command](a)
    except WRError as exc:
        raise SystemExit('Operazione non completata: ' + exc.message) from None
    except (ValueError, PermissionError, RuntimeError) as exc:
        raise SystemExit('Operazione non completata: ' + str(exc)) from None


if __name__ == '__main__':
    main()
