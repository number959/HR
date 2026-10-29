# NefroCenter WR · Work Resources 1.0 — installazione e avvio, passo per passo

Questa guida è scritta per chi non ha mai installato il portale. Segue tre percorsi, dal più semplice al più completo:

1. **Provarlo subito sul proprio computer** (dieci minuti, dati fittizi, nessun account da creare).
2. **Installarlo per davvero su un computer o server aziendale** (prima installazione, dati reali, account personali).
3. **Pubblicare la demo** (un sito statico con dati fittizi, per far vedere il portale a chi non lo ha installato).

Ogni comando va copiato così com'è nella finestra del terminale (Windows: PowerShell; Linux/macOS: Terminale). Le righe che iniziano con `#` sono commenti e non vanno eseguite.

---

## 0. Cosa scaricare e cosa serve

**Il pacchetto.** Scompattare `NefroCenter_WR_1.0.0.zip`: si ottiene la cartella `NefroCenter_WR_1.0.0/` con dentro `gestionale/` (il portale), `demo/` (la demo), `strumenti/` e i documenti. In alternativa, dal file `Codice_Sorgente_NefroCenter_WR_1.0.0.txt`: `python Codice_Sorgente_NefroCenter_WR_1.0.0.txt --directory NefroCenter_WR` ricrea la stessa cartella (vedere `SORGENTE_IN_TXT.md`).

**Python.** Serve Python **3.12 o 3.13** a 64 bit.

- Windows: scaricare da https://www.python.org/downloads/windows/ il programma di installazione «Windows installer (64-bit)». Durante l'installazione spuntare **«Add python.exe to PATH»**. Per controllare, aprire PowerShell e scrivere `py -3 --version`: deve rispondere `Python 3.12.x` o `3.13.x`.
- Linux (Debian/Ubuntu): `sudo apt install python3 python3-venv python3-pip`; controllare con `python3 --version`.
- macOS: `brew install python@3.13` oppure il programma di installazione da python.org; controllare con `python3 --version`.

**Un browser aggiornato** (Chrome, Edge, Firefox, Safari). **Un'app Authenticator** sul telefono (Microsoft Authenticator, Google Authenticator, FreeOTP…) per il portale aziendale: nella prova locale e nella demo non serve.

**Connessione a Internet** solo per installare le due librerie Python (`cryptography`, `tzdata`) la prima volta. Tutto il resto è incluso nel pacchetto.

---

## 1. Provarlo subito sul proprio computer (dati fittizi)

Questo percorso non crea nessuna installazione: avvia un portale di prova con tre strutture inventate e dodici persone inventate, che sparisce alla chiusura.

### 1.1 Aprire il terminale nella cartella giusta

- Windows: aprire la cartella `NefroCenter_WR_1.0.0\gestionale` in Esplora file, cliccare nella barra dell'indirizzo, scrivere `powershell` e premere Invio. Si apre PowerShell già nella cartella giusta.
- Linux/macOS: aprire il Terminale e scrivere `cd` seguito da uno spazio, poi trascinare la cartella `gestionale` nella finestra e premere Invio.

Controllare di essere nel posto giusto: il comando `dir` (Windows) o `ls` (Linux/macOS) deve mostrare `manage.py`, `wr`, `web`, `vendor`, `tests`, `strumenti`.

### 1.2 Creare l'ambiente Python e installare le due librerie

Windows (PowerShell):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Se PowerShell risponde «l'esecuzione di script è disabilitata», non serve attivare nulla: i comandi di questa guida chiamano sempre `.\.venv\Scripts\python.exe` direttamente.

### 1.3 Avviare il portale di prova

Windows:

```powershell
.\.venv\Scripts\python.exe strumenti\anteprima.py --port 8090
```

Linux/macOS:

```bash
.venv/bin/python strumenti/anteprima.py --port 8090
```

Il terminale scrive `Anteprima con dati fittizi (modalità demo): http://127.0.0.1:8090`. Aprire quell'indirizzo nel browser: compare la pagina «Prova la demo» con cinque profili (Amministratore, HR centrale, Responsabile, Compilatore, Direzione). Un clic sul profilo e si è dentro, senza password.

Per provare anche l'accesso vero (password e app Authenticator), avviare invece:

```bash
.venv/bin/python strumenti/anteprima.py --port 8092 --aziendale
```

Il terminale indica una cartella temporanea: dentro c'è `codici-attivazione.json` con un codice di attivazione per ciascuno dei cinque account di prova (`demo.admin`, `demo.hr`, `demo.manager`, `demo.operator`, `demo.viewer`). Nel browser scegliere «Usa il codice di attivazione», inserire nome utente e codice, scegliere una password e inquadrare il QR con l'app Authenticator.

Per fermare il portale di prova: `Ctrl+C` nel terminale. I dati di prova si cancellano da soli (cartella temporanea) oppure restano nella cartella indicata con `--dir`.

---

## 2. Installazione aziendale (dati reali)

### 2.1 Dove installarlo

Il portale va installato **una sola volta**, su un computer o server acceso durante l'orario di lavoro, raggiungibile dalle strutture. Le sedi lo usano dal browser: **non si installa nulla sui PC delle sedi**.

Due scelte possibili:

- **Server Linux con servizio automatico e HTTPS** (consigliato): il portale parte da solo all'accensione, i certificati e il nome del sito li gestisce il reverse proxy (Caddy o quello già in uso). È descritto al punto 2.5.
- **PC o server Windows**: il portale si avvia con un'attività pianificata; per l'HTTPS serve comunque un reverse proxy (Caddy funziona anche su Windows) oppure una VPN aziendale.

Cartelle consigliate (si possono cambiare, ma vanno usate sempre le stesse):

| Contenuto | Linux | Windows |
|---|---|---|
| Programma | `/opt/nefrocenter-wr/gestionale` | `C:\NefroCenterWR\gestionale` |
| Ambiente Python | `/opt/nefrocenter-wr/.venv` | `C:\NefroCenterWR\.venv` |
| Archivio, documenti, backup locali | `/var/lib/nefrocenter-wr` | `C:\NefroCenterWR\dati` |
| Chiave del server | `/etc/nefrocenter-wr/server.key` | `C:\NefroCenterWR\riservato\server.key` |
| Seconda copia dei backup | cartella del NAS montata sul server | cartella del NAS raggiungibile dal servizio |

La cartella dei dati e quella della chiave devono essere leggibili **solo** dall'utente che esegue il servizio e dagli amministratori. La chiave `server.key` serve a cifrare i segreti delle app Authenticator: **farne subito una copia protetta** (per esempio in un gestore di password aziendale); senza chiave, dopo un ripristino, tutti dovrebbero ricollegare l'app.

### 2.2 Preparare il programma

Copiare la cartella `gestionale` nel percorso scelto. Poi creare l'ambiente Python e installare le librerie (come al punto 1.2, ma nella cartella definitiva):

Linux:

```bash
cd /opt/nefrocenter-wr
python3 -m venv .venv
.venv/bin/python -m pip install -r gestionale/requirements.txt
```

Windows (PowerShell come amministratore):

```powershell
cd C:\NefroCenterWR
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r gestionale\requirements.txt
```

### 2.3 Creare l'archivio e il primo amministratore (solo la prima volta)

Il comando `init` chiede: nome utente dell'amministratore (per esempio `mario.rossi`), nome e cognome, nome e codice della prima struttura (il codice è una sigla come `CAPODICHINO`). Crea l'archivio, la chiave, il primo backup e stampa un **codice di attivazione** valido 7 giorni e una sola volta.

Linux:

```bash
sudo mkdir -p /var/lib/nefrocenter-wr /etc/nefrocenter-wr
sudo chown nefrocenter-wr:nefrocenter-wr /var/lib/nefrocenter-wr /etc/nefrocenter-wr   # l'utente di servizio, vedi 2.5
sudo -u nefrocenter-wr /opt/nefrocenter-wr/.venv/bin/python /opt/nefrocenter-wr/gestionale/manage.py init \
    --data-dir /var/lib/nefrocenter-wr --key-file /etc/nefrocenter-wr/server.key
```

Windows:

```powershell
mkdir C:\NefroCenterWR\dati, C:\NefroCenterWR\riservato
.\.venv\Scripts\python.exe gestionale\manage.py init --data-dir C:\NefroCenterWR\dati --key-file C:\NefroCenterWR\riservato\server.key
```

Copiare il codice di attivazione stampato e conservarlo con riservatezza: serve al primo accesso dell'amministratore. **Non eseguire mai `init` una seconda volta** sulla stessa cartella: il programma si rifiuta, ma è meglio non provarci.

### 2.4 Prima prova sul server stesso (HTTP locale)

Prima di configurare HTTPS conviene controllare che tutto funzioni sul computer dove è installato:

Linux:

```bash
/opt/nefrocenter-wr/.venv/bin/python /opt/nefrocenter-wr/gestionale/manage.py serve \
    --data-dir /var/lib/nefrocenter-wr --key-file /etc/nefrocenter-wr/server.key \
    --origin http://127.0.0.1:8080 --dev-http
```

Windows:

```powershell
.\.venv\Scripts\python.exe gestionale\manage.py serve --data-dir C:\NefroCenterWR\dati --key-file C:\NefroCenterWR\riservato\server.key --origin http://127.0.0.1:8080 --dev-http
```

Aprire `http://127.0.0.1:8080` **sullo stesso computer**: scegliere «Primo accesso», inserire nome utente e codice di attivazione, scegliere la password personale (almeno 12 caratteri), inquadrare il QR con l'app Authenticator e inserire il codice a 6 cifre, scaricare o stampare i codici di recupero. Si entra nel portale: la prima struttura è già creata, i parametri (fasce, causali, calendario) sono quelli iniziali da controllare in **Parametri struttura**.

`--dev-http` funziona solo su `127.0.0.1`: il portale rifiuta HTTP su un indirizzo di rete, quindi le sedi non possono ancora collegarsi. Fermare con `Ctrl+C` e passare al punto 2.5.

### 2.5 Servizio automatico e HTTPS (Linux)

1. **Utente di servizio** (senza accesso interattivo): `sudo useradd --system --home /var/lib/nefrocenter-wr --shell /usr/sbin/nologin nefrocenter-wr`. Dare a questo utente la proprietà di `/var/lib/nefrocenter-wr` e la lettura di `/opt/nefrocenter-wr` e della chiave.
2. **Variabili del servizio**: copiare `gestionale/deploy/wr.env.example` in `/etc/nefrocenter-wr/wr.env` e impostare `WR_ORIGIN=https://IL-NOME-DEL-SITO` (per esempio `https://wr.azienda.it`), `WR_DATA_DIR`, `WR_KEY_FILE`, `WR_PORT=8080`, `TZ=Europe/Rome`. Permessi `600`, proprietario l'utente di servizio.
3. **Servizio systemd**: copiare `gestionale/deploy/nefrocenter-wr.service` in `/etc/systemd/system/` (adattare i percorsi se diversi) e poi:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now nefrocenter-wr
   sudo systemctl status nefrocenter-wr          # deve dire "active (running)"
   sudo journalctl -u nefrocenter-wr -n 50        # le ultime righe del registro, in caso di problemi
   ```
4. **HTTPS con Caddy** (se non c'è già un reverse proxy): installare Caddy (https://caddyserver.com/docs/install), aggiungere al file `/etc/caddy/Caddyfile` il blocco di `gestionale/deploy/Caddyfile.example` con il nome vero del sito, poi `sudo caddy validate --config /etc/caddy/Caddyfile` e `sudo systemctl reload caddy`. Caddy ottiene e rinnova da solo il certificato se il nome del sito è raggiungibile da Internet sulle porte 80 e 443; per un sito solo interno usare i certificati della PKI aziendale. Il firewall deve lasciare passare 443 (e 80 per il rinnovo) **ma non 8080**, che resta interna.
5. **Prova dalla rete**: da un PC di una sede aprire `https://IL-NOME-DEL-SITO`, fare il primo accesso dell'amministratore (se non già fatto), registrare un turno di prova, scaricare un'esportazione. Riavviare il server e controllare che il portale riparta da solo.

### 2.6 Servizio automatico (Windows)

1. Aprire **Utilità di pianificazione** → **Crea attività**.
2. Generale: nome `NefroCenter WR`, «Esegui indipendentemente dalla connessione degli utenti», account dedicato (non l'amministratore personale), «Esegui con i privilegi più elevati» non necessario.
3. Attivazione: «All'avvio del sistema».
4. Azione: Avvio programma; Programma `C:\NefroCenterWR\.venv\Scripts\python.exe`; Argomenti `gestionale\manage.py serve --origin https://IL-NOME-DEL-SITO`; Inizia in `C:\NefroCenterWR`.
5. Impostazioni: «Se l'attività non riesce, riavvia ogni 1 minuto», «Arresta l'attività se è in esecuzione da più di» **deselezionato**.
6. Variabili d'ambiente: impostare a livello di sistema (Pannello di controllo → Sistema → Variabili d'ambiente) `WR_DATA_DIR=C:\NefroCenterWR\dati`, `WR_KEY_FILE=C:\NefroCenterWR\riservato\server.key`, `WR_PORT=8080`, `TZ=Europe/Rome`; riavviare l'attività.
7. HTTPS: installare Caddy per Windows con lo stesso blocco di configurazione del punto 2.5 (il proxy inoltra a `127.0.0.1:8080`), oppure usare la VPN aziendale con il proxy già esistente. Aprire nel firewall solo la porta del proxy.

### 2.7 Dopo l'installazione: i primi passi nel portale

1. **Parametri struttura**: fasce orarie, causali, ruoli, sedi esterne, festività (le nazionali ci sono già: aggiungere il patrono), pazienti di riferimento, tariffe proposte per gli accordi.
2. **Strutture**: creare le altre strutture (nome e codice) e compilare la **Rubrica strutture**.
3. **Accessi e ruoli**: un account per ogni persona (responsabili, compilatori, HR, direzione) con le strutture assegnate; consegnare di persona il codice di attivazione (vale 7 giorni).
4. **Persone e fascicoli**: inserire le persone di ogni struttura; per i collaboratori a prestazione indicare tipo di rapporto, chi fattura, ritenuta e cassa, IBAN.
5. **Backup**: dalla pagina Backup indicare la cartella del NAS già montata e fare «Copia e prova di ripristino». Finché non è fatta, i backup restano solo sul server.
6. **Posta e promemoria**: solo quando l'azienda ha scelto il servizio di posta (vedere `docs/POSTA.md`); la password va nella variabile `WR_SMTP_PASSWORD` del servizio, mai nel portale.
7. **Paghe**: concordare con il consulente il tracciato (`docs/PAGHE.md`) oppure usare il **foglio mensile come il modello Excel** dalle Esportazioni.
8. **Mesi passati**: importare i vecchi file Excel da **Importa Excel** (uno per struttura e mese) oppure, se si viene dalla 0.11, seguire `MIGRAZIONE_DALLA_0.11.md`.

### 2.8 Aggiornare, fermare, ripristinare

- **Fermare**: Linux `sudo systemctl stop nefrocenter-wr`; Windows: terminare l'attività pianificata.
- **Aggiornare**: fermare il servizio, fare un backup (`manage.py backup`), sostituire la cartella `gestionale` con la nuova versione, reinstallare `requirements.txt` se è cambiato, riavviare. Non eseguire `init`.
- **Controllare l'archivio**: `manage.py check --data-dir … --key-file …` (sola lettura: integrità, conteggi, stato dei backup).
- **Ripristinare un backup**: fermare il servizio, mettere da parte la cartella dati, copiare il file di backup come `wr.sqlite3` in una cartella dati pulita, rimettere la chiave, eseguire `manage.py after-restore` (revoca sessioni e codici di recupero, spegne posta e promemoria), riavviare.
- **Telefono perso**: la persona entra con password e un codice di recupero e ricollega il telefono da «Il mio account»; senza codici, l'amministratore genera un nuovo codice di attivazione da «Accessi e ruoli» (dal server: `manage.py activate --username NOME`).

### 2.9 Se qualcosa non va

| Sintomo | Cosa controllare |
|---|---|
| `python` non trovato | Python non installato o non nel PATH: usare `py -3` su Windows, `python3` su Linux/macOS |
| `pip install` fallisce | Serve Internet la prima volta; dietro un proxy aziendale impostare `HTTPS_PROXY` |
| «Indicare --origin» | Manca `WR_ORIGIN` (o `--origin`): deve essere l'indirizzo HTTPS del portale |
| «Archivio non trovato» | `--data-dir` sbagliato oppure `init` mai eseguito |
| Il browser dice «non sicuro» | HTTPS non configurato: le sedi devono usare l'indirizzo del proxy, mai `http://…:8080` |
| Codice dell'app rifiutato | Orologio del telefono o del server fuori sincronia (serve l'ora esatta); oppure codice già usato |
| 428 / «Conferma di sicurezza» | Operazione sensibile: reinserire password e codice dell'app (vale 5 minuti) |
| Nulla parte all'accensione | `systemctl status nefrocenter-wr` / registro dell'attività pianificata: di solito percorsi o permessi sbagliati |

---

## 3. La demo (sito statico con dati fittizi)

La demo fa girare **lo stesso motore** del portale dentro il browser (Pyodide): non serve un server Python, basta un servizio di pagine statiche. Non contiene dati reali e non invia email.

### 3.1 Costruirla

Dalla cartella `demo`:

```bash
python3 costruisci_demo.py                    # versione leggera (circa 3 MB): Pyodide viene scaricato dalla rete jsDelivr all'apertura
python3 costruisci_demo.py --includi-pyodide  # versione autonoma (circa 18 MB): funziona anche senza quella rete
```

Il risultato è la cartella `demo/dist/`. Nel pacchetto di consegna la versione leggera è già costruita in `NefroCenter_WR_Demo_1.0.0.zip`.

### 3.2 Provarla sul proprio computer

```bash
python3 avvia_demo.py            # poi aprire http://localhost:8000
python3 avvia_demo.py --lan      # anche dagli altri computer della stessa rete
```

Non basta fare doppio clic su `index.html`: la demo va servita via HTTP (il browser blocca i file locali).

### 3.3 Pubblicarla

Copiare il contenuto di `demo/dist/` su un servizio di siti statici con HTTPS (per esempio lo stesso servizio che ospita la demo della 0.11, GitHub Pages, Netlify, un bucket con sito statico, una cartella del server web aziendale). Nessuna configurazione lato server: tutti i file sono statici. Il file `index.html` contiene l'intestazione `Content-Security-Policy` che consente solo i file della demo e la rete di distribuzione di Pyodide. La demo della 0.11 resta al suo indirizzo finché l'azienda non decide di sostituirla.

---

## 4. Riepilogo dei comandi

```bash
# prova locale (dati fittizi)
python3 strumenti/anteprima.py --port 8090
python3 strumenti/anteprima.py --port 8092 --aziendale

# installazione aziendale
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py init  --data-dir DATI --key-file CHIAVE
.venv/bin/python manage.py serve --data-dir DATI --key-file CHIAVE --origin https://wr.azienda.it
.venv/bin/python manage.py check --data-dir DATI --key-file CHIAVE
.venv/bin/python manage.py backup --data-dir DATI --key-file CHIAVE
.venv/bin/python manage.py migra-011 --source presenze.sqlite3 --legacy-key chiave-0.11.key --data-dir DATI --key-file CHIAVE

# prove e controlli (sviluppo)
python3 -m unittest discover -s tests -p "test_*.py"
node ../strumenti/giro_interfaccia.cjs CARTELLA http://127.0.0.1:8090

# demo
cd ../demo && python3 costruisci_demo.py && python3 avvia_demo.py
```
