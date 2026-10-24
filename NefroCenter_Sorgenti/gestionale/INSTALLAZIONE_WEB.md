# Attivazione di Persone e Presenze Web 0.11 — edizione qualità 0.11.1

Questa guida descrive l’installazione del gestionale operativo su un server aziendale. La demo pubblica è un sito separato con dati fittizi: https://nefrocenter-demo.icy-bass-2671.chatgpt.site. Il gestionale aziendale non è ancora installato.

L’edizione qualità 0.11.1 migliora guide, video e documentazione; la versione funzionale resta 0.11 e lo schema database è 8. Leggere anche `INSTALLAZIONE_IN_BREVE.md`, `AGGIORNAMENTO_0.11.md` e `AGGIORNAMENTO_0.11.1.md`.

## Aggiornare un’installazione web esistente

Fermare il servizio e conservare una copia verificata del programma precedente, del database, della chiave 2FA e della configurazione. Estrarre il nuovo codice in una directory separata e mantenere i percorsi dati e chiave già in uso. **Non eseguire `manage.py init` su un archivio esistente.**

All’avvio, `core.init_db()` controlla lo schema e crea una copia prima delle modifiche additive previste per lo schema 8. Seguire `AGGIORNAMENTO_0.11.md`; non applicare alla versione attuale le sole indicazioni delle revisioni storiche 0.6–0.8. Dopo l’aggiornamento verificare accesso con 2FA, fascicoli, allegati, presenze e nuove pagine. Approvazioni e promemoria richiedono attivazione esplicita nella configurazione operativa.

Per il ripristino completo del codice e dei dati seguire `ROLLBACK.md`, usando l’archivio compatibile con quella versione. La scelta dello stile modifica soltanto l’aspetto dell’interfaccia.

## Scelta senza nuovi abbonamenti

Usare un server o PC aziendale già disponibile, acceso quando le sedi lavorano, con backup separati e connessione affidabile. Un server Linux con Python e un reverse proxy HTTPS è il percorso suggerito. Anche Windows può eseguire il servizio Python; non serve installare l’EXE nelle postazioni dei compilatori.

I client usano solo il browser. Non servono Drive, Syncthing o un database per ogni sede. La gestione del server resta necessaria: “gratuito” significa assenza di licenze e abbonamenti software aggiuntivi, usando risorse già possedute. L’hosting della demo non fornisce il server né l’archivio aziendale.

Per l’accesso remoto scegliere con il tecnico:

- **VPN aziendale esistente + HTTPS interno**, se tutte le sedi possono raggiungere il server tramite VPN;
- **HTTPS pubblico su un sottodominio già posseduto**, con DNS e rete configurati per quel server. Il certificato può essere gestito dal reverse proxy. Non pubblicare direttamente la porta applicativa 8080.

Non vengono forniti un dominio registrato, un IP pubblico o accesso alla rete del gruppo. Un semplice hosting di pagine statiche non esegue questo servizio Python e non sostituisce il database.

## Requisiti

Python 3.12 o 3.13 a 64 bit, accesso al disco locale per archivio/backup e un reverse proxy HTTPS già gestito oppure Caddy. Internet è necessario per installare le dipendenze `cryptography` e `tzdata` definite in `requirements.txt` la prima volta; PyOTP, Segno, Waitress e XlsxWriter sono già inclusi. Browser aggiornati. Orologio di server e telefoni sincronizzato: i codici TOTP dipendono dall’ora.

L’architettura usa un processo applicativo e SQLite con WAL. Non avviare più istanze con archivi diversi per lo stesso portale. Non sono stati dimensionati il massimo numero di utenti o l’alta disponibilità della rete reale: effettuare il collaudo con il carico atteso prima dell’estensione a tutte le sedi.

## Prova sul PC del tecnico

Estrarre il pacchetto in una cartella privata. Esempio Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py init --data-dir data --key-file private/server.key
.\.venv\Scripts\python.exe web_server.py --data-dir data --key-file private/server.key --origin http://127.0.0.1:8080 --dev-http
```

Esempio Linux, nella cartella del progetto:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py init --data-dir data --key-file private/server.key
.venv/bin/python web_server.py --data-dir data --key-file private/server.key --origin http://127.0.0.1:8080 --dev-http
```

`manage.py init` chiede referente, primo centro, nome utente e password iniziale. Crea la chiave privata una sola volta e stampa il codice di attivazione del primo amministratore. Conservare quel codice riservatamente. Non esistono credenziali precompilate.

Aprire `http://127.0.0.1:8080` sullo stesso computer. Inserire le credenziali, il codice di attivazione, configurare un’app TOTP e scegliere la password personale. Il servizio non accetta una configurazione HTTP per un indirizzo pubblico o LAN: `--dev-http` è limitato al loopback e serve solo al collaudo. La prova locale non rende il portale raggiungibile dalle sedi.

## Installazione Linux sul server

Esempio di percorsi da adattare:

| Contenuto | Percorso |
|---|---|
| Codice e ambiente Python | `/opt/presenze-web` |
| Database e backup | `/var/lib/presenze-web` |
| Chiave dei segreti 2FA | `/etc/presenze-web/server.key` |
| Configurazione del servizio | `/etc/presenze-web/presenze.env` |

1. Creare un utente di servizio dedicato `presenze-web`, senza accesso interattivo. Copiare il codice in `/opt/presenze-web`. Il servizio deve poter leggere il codice senza modificarlo.
2. Creare l’ambiente virtuale con Python e installare `requirements.txt`. Assegnare all’utente di servizio scrittura solo sull’archivio e sui backup. Rendere la chiave leggibile esclusivamente all’utente del servizio e agli amministratori autorizzati.
3. Eseguire l’inizializzazione come utente del servizio con percorsi assoluti. La directory della chiave deve esistere con permessi adatti a questa inizializzazione; dopo, il servizio ha bisogno solo di leggere la chiave.

```bash
sudo -u presenze-web /opt/presenze-web/.venv/bin/python /opt/presenze-web/manage.py init --data-dir /var/lib/presenze-web --key-file /etc/presenze-web/server.key
```

4. Copiare `deploy/presenze.env.example` in `/etc/presenze-web/presenze.env`, impostando `PRESENZE_ORIGIN` al vero indirizzo HTTPS, senza percorsi. Non contiene password: la chiave rimane nel file riservato.
5. Adattare e installare `deploy/presenze-web.service` in `/etc/systemd/system/`, quindi avviare il servizio:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now presenze-web
sudo systemctl status presenze-web
```

6. Configurare HTTPS. `deploy/Caddyfile.example` è un blocco da aggiungere al Caddyfile esistente, non un sostituto di eventuali altri siti. Sostituire il nome di esempio con il dominio vero e verificare DNS, certificato e raggiungibilità. Controllare con `caddy validate --config /etc/caddy/Caddyfile` prima della ricarica. Per HTTPS interno utilizzare certificati considerati attendibili dai PC aziendali, secondo la PKI o il proxy già in uso.
7. Il proxy inoltra all’app solo su `127.0.0.1:8080` e fornisce l’IP remoto. Non rendere 8080 accessibile alle sedi; non esporre database, chiave, backup o sorgenti come file web.
8. Provare accesso completo con 2FA da una sede pilota, permessi del compilatore, creazione di una presenza e consultazione da Direzione. Poi eseguire prova di backup, ripristino e riavvio del servizio. Questi controlli sulla rete reale non sono stati eseguiti durante la consegna.

Su Windows il server Python può essere avviato mediante un’attività pianificata aziendale con account dedicato e cartelle protette; l’azione punta all’interprete `.venv\Scripts\python.exe`, allo script `web_server.py` e ai percorsi/origine HTTPS definitivi. Impostare avvio all’accensione, riavvio in caso di errore e accesso al disco. Reverse proxy, certificato e firewall restano da configurare sul server reale.

## Creare gli account delle sedi

L’amministratore apre **Utenti e permessi → Nuovo utente**, assegna ruolo e centri e imposta la password iniziale. Dopo il salvataggio viene mostrato una sola volta il codice di attivazione. Consegnare le credenziali tramite canali riservati già adottati dall’organizzazione: la creazione dell’account non invia automaticamente questi dati per email. Le comunicazioni aziendali hanno una configurazione SMTP separata, inizialmente disattivata.

- HR centrale: consulta tutti i centri e gestisce fascicoli, documenti, identità e decorrenze; non amministra utenti o backup tecnici.
- Responsabile: gestisce persone, fascicoli e parametri dei centri assegnati.
- Compilatore: inserisce le presenze secondo i permessi concessi.
- Direzione / lettore: consulta i centri assegnati e il riepilogo.
- Amministratore: accesso e gestione su tutti i centri, inclusi gli utenti.

Tutti configurano 2FA al primo accesso. Ogni cambio di ruolo, centro assegnato, password amministrativa o stato dell’account revoca le sessioni della persona.

## Migrare i dati delle versioni EXE

1. In ogni sede completare le ultime modifiche e creare un backup dalla 0.4. Fermare poi le scritture negli EXE: il passaggio è una migrazione, non una sincronizzazione bidirezionale.
2. Trasferire riservatamente i backup completi sul server; non usare i pacchetti `.pcsync`, che escludono i fascicoli HR.
3. Fare un backup dell’archivio web e arrestare il servizio durante la migrazione. Importare un file alla volta:

```bash
/opt/presenze-web/.venv/bin/python /opt/presenze-web/migrate_desktop.py /percorso/backup_sede.sqlite3 --data-dir /var/lib/presenze-web
```

4. Il programma crea una copia preventiva e importa in un’unica transazione. Gli account locali, le credenziali di sincronizzazione e le sessioni non vengono importati. Ricreare gli account web con 2FA e assegnare i centri corretti.
5. Confrontare persone, mesi, ore, documenti e parametri con gli archivi originali. I codici centro che collidono ricevono un suffisso. Il medesimo file non può essere importato due volte; backup diversi della stessa sede non vengono riconosciuti e fusi automaticamente: usare un solo backup autorevole per sede.
6. Riavviare il servizio e fare compilare da browser. Conservare gli archivi originali secondo le procedure aziendali.

## Backup, chiave e ripristino

L’app crea un backup verificato per giorno mentre il servizio è acceso e controlla ogni ora il cambio di data. Copie aggiuntive: **Backup ed esportazioni → Crea backup adesso** (amministratore), oppure:

```bash
.venv/bin/python manage.py backup --data-dir /var/lib/presenze-web --key-file /etc/presenze-web/server.key
```

Dalla stessa pagina l’amministratore può scaricare le ultime 50 copie elencate, fino a 256 MiB ciascuna, previa verifica recente con password e 2FA. Le copie più grandi vanno prelevate dal server. Le copie locali non vengono eliminate automaticamente. La seconda copia su NAS si configura in **Backup ed esportazioni → Copia su destinazione separata**: percorso assoluto di una cartella già montata e accessibile all’account di servizio, numero di copie (0 = tutte), intervallo della prova tecnica. Nessun trasferimento parte finché la funzione è disattivata. La conservazione riguarda esclusivamente copie NAS gestite e verificate.

Conservare una copia separata dei backup completati e **della chiave originale `server.key`**. La chiave non è inclusa nel backup SQLite; senza di essa i segreti 2FA cifrati non sono recuperabili. Le copie contengono dati del personale: accessi e conservazione devono essere definiti. Non sincronizzare il database attivo con Drive/OneDrive.

Per ripristinare: fermare il servizio, conservare la directory dati attuale, predisporre una directory dati pulita, copiarvi il backup come `presenze.sqlite3` e ripristinare la chiave corrispondente. Prima di riaprire gli accessi eseguire:

```bash
.venv/bin/python manage.py after-restore --data-dir /var/lib/presenze-web --key-file /etc/presenze-web/server.key
```

Il comando chiede conferma e invalida sessioni, codici di recupero e attivazioni presenti nel backup, evitando di riattivare codici già usati dopo quella copia. Authenticator continua a funzionare per gli account attivi; ciascuno dovrà rigenerare i codici di recupero. I nuovi utenti ancora in attivazione richiedono un nuovo codice dall’amministratore. Infine riavviare e confrontare i dati.

## Telefono o password persi

Con password e codice di recupero si può accedere e sostituire Authenticator. Se i recuperi non sono disponibili, un amministratore verifica la persona e usa **Ripristina 2FA**, indicando il motivo.

Se nessun amministratore riesce ad accedere, il referente con accesso amministrativo al server può usare la console locale, dopo la verifica d’identità prevista:

```bash
.venv/bin/python manage.py activate --username NOME_UTENTE --data-dir /var/lib/presenze-web --key-file /etc/presenze-web/server.key
.venv/bin/python manage.py reset-password --username NOME_UTENTE --data-dir /var/lib/presenze-web --key-file /etc/presenze-web/server.key
```

Il primo comando revoca il vecchio 2FA e crea una nuova attivazione; il secondo modifica solo la password e mantiene il 2FA. Non esiste un recupero aperto da Internet né una password di servizio universale.

## Riferimenti

- PyOTP: https://pyauth.github.io/pyotp/
- RFC 6238: https://www.rfc-editor.org/rfc/rfc6238.html
- OWASP MFA: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- Fernet: https://cryptography.io/en/latest/fernet/
- Waitress e reverse proxy: https://docs.pylonsproject.org/projects/waitress/en/stable/reverse-proxy.html
- HTTPS automatico Caddy: https://caddyserver.com/docs/automatic-https

Le licenze gratuite non certificano da sole conformità, sicurezza del server o correttezza degli adempimenti del personale.


## Console per la seconda copia su NAS

Creare un file JSON con `enabled`, `destination`, `retention_count` e `probe_interval_days`. Per esempio, dopo avere predisposto la cartella reale:

```json
{"enabled": true, "destination": "/mnt/nas/presenze", "retention_count": 30, "probe_interval_days": 30}
```

```bash
.venv/bin/python manage.py backup-config --data-dir /var/lib/presenze-web --policy-file /percorso/nas.json
.venv/bin/python manage.py backup-probe --data-dir /var/lib/presenze-web
.venv/bin/python manage.py backup-status --data-dir /var/lib/presenze-web
```

`backup-sync` esegue una copia immediata; `backup-probe` crea una nuova copia e la verifica anche mediante lettura su copia temporanea. Il controllo automatico avviene ogni ora mentre il servizio è acceso, con al massimo una copia automatica al giorno riuscita. La configurazione e l’esito sono nei file `backup_policy.json` e `backup_status.json` della cartella dati: conservarli per riattivare la stessa politica dopo un ripristino. Questi file non contengono credenziali NAS e non sono inclusi nel backup SQLite.

La versione 0.11 richiede anche `tzdata` (in `requirements.txt`) per il fuso Europe/Rome dei promemoria, incluso il cambio ora solare/legale, anche sui sistemi senza database dei fusi installato.
