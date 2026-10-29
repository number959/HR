# Installare NefroCenter WR · Work Resources 1.0

**Il portale si installa una sola volta su un server aziendale.** Le strutture e l'ufficio HR lo aprono dal browser allo stesso indirizzo HTTPS. Non c'è nulla da installare sui PC delle sedi né sui telefoni, a parte un'app Authenticator per il secondo fattore.

Questa guida è il riferimento tecnico; la versione passo per passo, con tutti i comandi per Windows e Linux e la demo, è `INSTALLAZIONE_PASSO_PASSO.md`. Questa guida è per il tecnico. Per chi usa il portale: la **Guida** dentro il portale (menu Aiuto), il manuale illustrato e le videoguide in `web/help/`.

## Cosa serve

- Un server Linux (consigliato) o Windows, acceso durante l'orario di lavoro, con disco locale per archivio, documenti e backup.
- **Python 3.12 o 3.13 a 64 bit**. Le uniche librerie da installare sono in `requirements.txt` (`cryptography`, `tzdata`); le altre sono incluse nella cartella `vendor/` con le rispettive licenze.
- Un indirizzo HTTPS raggiungibile dalle sedi (VPN aziendale oppure dominio e reverse proxy). Il proxy gestisce il certificato e inoltra al servizio locale sulla porta 8080, che resta interna al server.
- Una cartella del **NAS** montata sul server per la seconda copia dei backup: percorso e permessi li decide il tecnico; il portale non contiene destinazioni preimpostate.
- Per le email, un servizio **SMTP aziendale** con TLS: non è ancora stato scelto. Finché non c'è, modelli, liste, bozze e anteprime funzionano lo stesso e nessuna email parte.
- Orologio del server e dei telefoni sincronizzato: i codici dell'app Authenticator dipendono dall'ora.

Un hosting che serve solo pagine statiche **non** può ospitare il portale aziendale (serve il motore Python). La demo pubblica, invece, è un sito statico separato con dati fittizi: vedere `../demo/LEGGIMI.md`.

## Prova sul PC del tecnico

Dalla cartella `gestionale`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py init --data-dir data --key-file private/server.key
.venv/bin/python manage.py serve --data-dir data --key-file private/server.key --origin http://127.0.0.1:8080 --dev-http
```

Su Windows (PowerShell) l'interprete è `.\.venv\Scripts\python.exe`.

`manage.py init` chiede nome utente e nome del primo amministratore, nome e codice della prima struttura; crea l'archivio `wr.sqlite3`, la chiave del server (una sola volta), il primo backup e stampa il **codice di attivazione** dell'amministratore (vale 7 giorni, una sola volta). Non esistono account o password preimpostati.

Aprire `http://127.0.0.1:8080`, scegliere **Primo accesso**, inserire nome utente e codice, poi scegliere la password personale (almeno 12 caratteri) e collegare l'app Authenticator con il codice QR. Conservare i codici di recupero.

`--dev-http` vale solo per `127.0.0.1`: il servizio rifiuta HTTP su un indirizzo di rete. Non rende il portale raggiungibile dalle sedi.

Per provare il portale con dati inventati, senza creare un'installazione: `python3 strumenti/anteprima.py` (vedere il commento in testa al file).

## Installazione sul server Linux

| Contenuto | Percorso consigliato |
|---|---|
| Programma e ambiente Python | `/opt/nefrocenter-wr` (dentro: `gestionale/`, `.venv/`) |
| Archivio, documenti e backup locali | `/var/lib/nefrocenter-wr` |
| Chiave del server | `/etc/nefrocenter-wr/server.key` |
| Configurazione del servizio | `/etc/nefrocenter-wr/wr.env` |
| Seconda copia dei backup | cartella separata sul NAS, configurata dal portale |

1. Creare l'utente di servizio `nefrocenter-wr` senza accesso interattivo. Copiare la cartella `gestionale` in `/opt/nefrocenter-wr/gestionale` (il servizio deve poterla leggere, non scrivere).
2. Creare l'ambiente virtuale e installare `requirements.txt`:
   ```bash
   cd /opt/nefrocenter-wr && python3 -m venv .venv && .venv/bin/python -m pip install -r gestionale/requirements.txt
   ```
3. Inizializzare **solo se è una nuova installazione** (per passare dalla 0.11 vedere `MIGRAZIONE_DALLA_0.11.md`):
   ```bash
   sudo -u nefrocenter-wr /opt/nefrocenter-wr/.venv/bin/python /opt/nefrocenter-wr/gestionale/manage.py init \
       --data-dir /var/lib/nefrocenter-wr --key-file /etc/nefrocenter-wr/server.key
   ```
   La cartella `/etc/nefrocenter-wr` deve esistere ed essere scrivibile dall'utente del servizio durante questo comando; dopo basta la lettura. `init` si rifiuta di toccare un archivio già esistente.
4. Copiare `deploy/wr.env.example` in `/etc/nefrocenter-wr/wr.env` e impostare `WR_ORIGIN` con l'indirizzo HTTPS vero (senza percorsi).
5. Installare il servizio: copiare `deploy/nefrocenter-wr.service` in `/etc/systemd/system/`, poi
   ```bash
   sudo systemctl daemon-reload && sudo systemctl enable --now nefrocenter-wr && sudo systemctl status nefrocenter-wr
   ```
6. Configurare HTTPS: `deploy/Caddyfile.example` è un blocco da aggiungere al Caddyfile esistente (o l'equivalente per il proxy in uso). Il proxy inoltra solo a `127.0.0.1:8080` e passa l'indirizzo del client (`X-Forwarded-For`, `X-Forwarded-Proto`). Non esporre la porta 8080, l'archivio, la chiave, i backup o i sorgenti.
7. Collaudo: primo accesso con app Authenticator da una sede pilota, registrazione di un turno, consultazione da Direzione, backup, riavvio del servizio. Questi controlli sulla rete aziendale **non** sono stati eseguiti durante lo sviluppo.

Su Windows il servizio si avvia con un'attività pianificata (account dedicato, avvio all'accensione, riavvio in caso di errore) che esegue `.venv\Scripts\python.exe manage.py serve` con le stesse variabili d'ambiente; proxy HTTPS e firewall restano da configurare.

## Variabili e comandi

| Variabile | Significato |
|---|---|
| `WR_DATA_DIR` | cartella dell'archivio (`wr.sqlite3`), dei documenti e dei backup locali |
| `WR_KEY_FILE` | chiave del server (cifra i segreti dell'app Authenticator) |
| `WR_ORIGIN` | indirizzo pubblico del portale, per esempio `https://wr.azienda.it` |
| `WR_PORT` | porta locale (predefinita 8080) |
| `WR_SMTP_PASSWORD` | password dell'account di posta: solo nell'ambiente del servizio, mai nell'archivio |

`manage.py` (sempre con `--data-dir` e `--key-file`, oppure con le variabili sopra):

| Comando | Cosa fa |
|---|---|
| `init` | nuova installazione (rifiuta un archivio esistente) |
| `serve` | avvia il servizio web (`--origin`, `--port`, `--dev-http` solo in locale) |
| `check` | controllo in sola lettura: integrità, conteggi, stato dei backup |
| `backup` | backup locale verificato, subito |
| `backup-config --policy-file file.json` | configura la seconda copia (`enabled`, `destination`, `retention_count`, `probe_interval_days`) |
| `backup-status`, `backup-sync`, `backup-probe` | stato, copia immediata, copia con prova di ripristino |
| `activate --username NOME` | nuovo codice di attivazione (telefono o password persi); revoca il vecchio secondo fattore |
| `after-restore` | da eseguire **dopo** un ripristino: revoca sessioni e codici di recupero, spegne posta e promemoria |
| `migra-011 --source presenze.sqlite3 [--legacy-key chiave-0.11.key]` | crea un archivio WR da un archivio 0.11 (che resta invariato) |
| `demo-data` | archivio di prova con dati fittizi, solo per lo sviluppo |

Nessun comando cancella dati.

## Account e ruoli

L'amministratore crea gli account da **Accessi e ruoli → Nuovo account**: nome utente, nome, ruolo, strutture. Il portale mostra una sola volta il codice di attivazione, da consegnare di persona o con un canale riservato: non lo invia per email. Ruoli: **Amministratore** (tutto), **HR centrale** (persone, documenti, approvazioni finali, paghe, comunicazioni di tutte le strutture), **Responsabile** (presenze, parametri, persone e chiusura del mese delle strutture assegnate), **Compilatore** (presenze delle strutture assegnate, con i permessi scelti nei parametri), **Direzione** (sola consultazione). La pagina **Ruoli e permessi** del portale elenca ogni permesso.

Operazioni sensibili (accessi, backup, paghe, invii, importazioni) chiedono di nuovo password e codice: la conferma vale 5 minuti. La sessione scade dopo 15 minuti senza attività.

## Backup, NAS e ripristino

Il servizio crea da solo un backup verificato al giorno in `WR_DATA_DIR/backups`; l'amministratore può crearne altri dalla pagina **Backup** e scaricare gli ultimi. Le copie locali non vengono cancellate automaticamente.

La **seconda copia** va su una cartella separata già montata sul server (il NAS): dalla pagina Backup, oppure con `manage.py backup-config`, indicare percorso assoluto, numero di copie da conservare (0 = tutte) e ogni quanti giorni fare la prova di ripristino. Finché non è attiva non parte nessun trasferimento. Il portale rifiuta cartelle dentro la cartella dei dati o con collegamenti simbolici.

Conservare **separatamente** una copia della chiave `server.key`: non è nel backup e senza di essa i segreti dell'app Authenticator non si recuperano. I documenti HR sono dentro l'archivio SQLite, quindi nel backup.

Per ripristinare: fermare il servizio, mettere da parte la cartella dati attuale, copiare il backup come `wr.sqlite3` in una cartella dati pulita, rimettere la chiave corrispondente, eseguire `manage.py after-restore` (chiede conferma), riavviare e confrontare i dati. Le email già accettate dal server di posta non si annullano ripristinando un backup: verificare lo storico del fornitore prima di riattivare gli invii.

## Posta, promemoria e paghe

- **Posta**: da **Comunicazioni → Server di posta** l'amministratore indica server, porta, sicurezza (SSL o STARTTLS), utente e mittente; la password va in `WR_SMTP_PASSWORD`. Non attivare l'invio con dati presunti: prima concordare il servizio con il fornitore e fare una prova con un indirizzo autorizzato. Ogni email ha un solo destinatario; l'accettazione del server non è conferma di lettura.
- **Promemoria** automatici: arrivano spenti. Si attivano solo dopo la posta, da **Promemoria**, confermando destinatari e anteprima. Il server deve essere acceso all'ora prevista (fuso Europe/Rome).
- **Paghe**: il tracciato del consulente non è ancora noto. In **Paghe → Tracciato del consulente** si importano le intestazioni o le specifiche concordate e si collauda un mese pilota; fino ad allora si scarica solo il prospetto di controllo.

## Telefono o password persi

Con password e un codice di recupero la persona entra e collega il nuovo telefono da **Il mio account**. Senza codici, un amministratore verifica l'identità e genera un nuovo codice di attivazione da **Accessi e ruoli**. Se nessun amministratore può entrare, dal server: `manage.py activate --username NOME` (chiede il motivo e conferma). Non esistono password universali né recuperi via Internet.

## Aggiornamenti

Prima di aggiornare: fermare il servizio, fare un backup (`manage.py backup`) e conservare chiave e configurazione. Sostituire la cartella `gestionale` con la nuova versione, reinstallare `requirements.txt` se cambiato, riavviare. Al primo avvio il programma applica da solo le modifiche dell'archivio necessarie (dopo un backup automatico). Non eseguire mai `init` su un archivio esistente.
