"""Local administration. No public bootstrap or unauthenticated reset route."""
import argparse,getpass,json,os,secrets,sys
from pathlib import Path
import core
from web_auth import Auth

def main():
    p=argparse.ArgumentParser(description='Amministrazione locale Presenze Web')
    p.add_argument('command',choices=['init','activate','reset-password','backup','after-restore','backup-config','backup-status','backup-sync','backup-probe'])
    p.add_argument('--data-dir',type=Path,default=Path(os.environ.get('PRESENZE_DATA_DIR','data')))
    p.add_argument('--key-file',type=Path,default=Path(os.environ.get('PRESENZE_KEY_FILE','private/server.key')))
    p.add_argument('--policy-file',type=Path,help='File JSON configurazione NAS; nessuna credenziale')
    p.add_argument('--username');a=p.parse_args();core.DB=a.data_dir.resolve()/'presenze.sqlite3'
    existed=core.DB.exists()
    if a.command=='init':
        if existed:
            import sqlite3
            with sqlite3.connect(core.DB) as c:
                if c.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone() and c.execute('SELECT 1 FROM users').fetchone():raise SystemExit('Archivio già inizializzato. Non viene modificato.')
        if not a.key_file.exists():Auth.create_key(a.key_file)
        core.init_db();auth=Auth(a.key_file)
        username=a.username or input('Nome utente amministratore: ').strip()
        name=input('Nome del referente: ').strip();center=input('Nome primo centro: ').strip()
        password=getpass.getpass('Password iniziale (almeno 12 caratteri): ')
        if password!=getpass.getpass('Ripeti password: '):raise SystemExit('Password diverse. Nessun account creato.')
        core.setup(dict(username=username,name=name,center_name=center,password=password))
        with core.connect() as c:uid=c.execute('SELECT id FROM users').fetchone()[0]
        code=auth.activation(uid,{'username':'console'},'Primo amministratore')
        print('Account creato. Codice di attivazione 2FA, valido 7 giorni (conservarlo riservatamente):\n'+code)
        print('Al primo accesso imposterai la tua password definitiva e l’app Authenticator.')
        core._backup();return
    if not existed:raise SystemExit('Database non trovato. Verificare --data-dir.')
    core.init_db()
    if a.command.startswith('backup-'):
        import backup_policy
        if a.command=='backup-config':
            if not a.policy_file:raise SystemExit('Specificare --policy-file con la configurazione JSON.')
            result=backup_policy.configure(core,json.loads(a.policy_file.read_text()))
        elif a.command=='backup-status':result=backup_policy.console_status(core)
        else:
            core._backup();result=backup_policy.run(core,force=True,probe=a.command=='backup-probe')
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    auth=Auth(a.key_file)
    if a.command=='backup':print(core._backup()['filename']);return
    if a.command=='after-restore':
        answer=input('Revocare sessioni e recuperi, disabilitare SMTP e sospendere le email pendenti del backup ripristinato? Scrivere CONFERMO: ')
        if answer!='CONFERMO':raise SystemExit('Nessuna modifica.')
        with core.connect() as c:
            c.execute('DELETE FROM web_sessions')
            c.execute("UPDATE web_security SET recovery='[]',activation='',activation_until=0,version=version+1")
            config=c.execute('SELECT data FROM communication_settings WHERE id=1').fetchone()
            if config:
                settings=json.loads(config['data']);settings['enabled']=False
                c.execute('UPDATE communication_settings SET version=version+1,data=? WHERE id=1',(core.dump(settings),))
            reason='Archivio ripristinato: verificare gli invii presso il servizio di posta prima di preparare nuove comunicazioni.'
            c.execute("UPDATE communication_recipients SET status='uncertain',error=?,batch_id='' WHERE status IN ('pending','sending')",(reason,))
            c.execute("UPDATE communication_attempts SET status='uncertain',finished_at=?,error=? WHERE status='sending'",(core.now(),reason))
            core.reminders.after_restore(core,c)
            auth.event(c,{'username':'console'},'Sessioni e recuperi invalidati dopo ripristino');c.commit()
        print('Sessioni e codici di recupero revocati. Gli utenti attivi possono accedere con Authenticator e rigenerare i codici. Gli account da attivare richiedono un nuovo codice di attivazione. SMTP e promemoria automatici disabilitati; le email pendenti sono sospese con esito incerto. Verificare lo storico del servizio di posta prima di preparare nuove bozze.');return
    if not a.username:raise SystemExit('Specificare --username.')
    with core.connect() as c:row=c.execute('SELECT * FROM users WHERE username=?',(a.username.casefold(),)).fetchone()
    if not row:raise SystemExit('Account non trovato.')
    reason=input('Motivo e riferimento della verifica d’identità: ').strip()
    if len(reason)<8:raise SystemExit('Motivazione troppo breve.')
    if a.command=='activate':
        answer=input('Revocare il secondo fattore e tutte le sessioni di '+a.username+'? Scrivere CONFERMO: ')
        if answer!='CONFERMO':raise SystemExit('Nessuna modifica.')
        print('Nuovo codice di attivazione, valido 7 giorni:\n'+auth.activation(row['id'],{'username':'console'},reason))
    else:
        password=getpass.getpass('Nuova password temporanea: ')
        if password!=getpass.getpass('Ripeti password: '):raise SystemExit('Password diverse.')
        credential=core.password_hash(password)
        with core.connect() as c:
            c.execute('UPDATE users SET credential=? WHERE id=?',(credential,row['id']))
            auth.event(c,{'username':'console'},'Password ripristinata da console',a.username+': '+reason);c.commit()
        auth.revoke(row['id']);print('Password aggiornata; 2FA mantenuto. Sessioni revocate.')

if __name__=='__main__':main()
