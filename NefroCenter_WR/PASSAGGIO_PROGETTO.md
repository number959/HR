# Passaggio del progetto — NefroCenter WR · Work Resources 1.0

Stato al **29 ottobre 2026**. Versione del programma **1.0.0**, schema dell'archivio WR **1**. Questo documento serve a chi riprende il lavoro (una persona o un assistente di programmazione come Claude Code): raccoglie contesto, decisioni già prese e regole da rispettare. Non contiene credenziali e non autorizza installazioni aziendali, invii reali o cancellazioni.

## 1. Come consegnare il progetto

Il progetto si consegna in due forme equivalenti, prodotte da `strumenti/consegna.py`:

- `NefroCenter_WR_1.0.0.zip`: l'intera cartella `NefroCenter_WR/` (gestionale, demo, strumenti, documenti, manuale e videoguide).
- `Codice_Sorgente_NefroCenter_WR_1.0.0.txt`: gli stessi file in un unico testo che è anche uno script Python (`python Codice_Sorgente_NefroCenter_WR_1.0.0.txt --directory NefroCenter_WR` li ricrea verificando le impronte; vedere `SORGENTE_IN_TXT.md`).

Aprire l'assistente nella cartella `NefroCenter_WR` e indicargli: «Leggi `CLAUDE.md` e `PASSAGGIO_PROGETTO.md`, poi `gestionale/VERIFICA.md` e `gestionale/STATO_PROGETTO.json`. Controlla quali file e strumenti sono presenti. Conserva il lavoro esistente e prosegui con la mia richiesta, distinguendo la demo pubblica dal portale aziendale.»

Il repository Git di lavoro contiene anche la cartella `NefroCenter_Sorgenti/` con la versione 0.11 (codice, documenti e media della vecchia versione): serve come riferimento e per la migrazione; non va modificata.

## 2. Obiettivo e stato effettivo

NefroCenter WR è il portale centrale del personale delle strutture NefroCenter: presenze e pianificazione, controlli e chiusura del mese, approvazione mensile, accordi e calcoli, persone e fascicoli, documenti con verifica HR, personale di gruppo, copertura turni e sostituzioni, uscite e dotazioni, rubrica strutture, comunicazioni, promemoria, paghe, statistiche ed esportazioni, backup, importazione del modello Excel, migrazione dalla 0.11.

- Il **portale aziendale non è installato** su un server dell'azienda. Posta, NAS e tracciato paghe **non sono configurati**: il programma li tiene spenti finché il tecnico non inserisce parametri reali e verificati.
- La **demo pubblica WR non è pubblicata**: si costruisce con `demo/costruisci_demo.py` e si prova in locale con `demo/avvia_demo.py`. La demo della 0.11 resta all'indirizzo indicato nella documentazione della 0.11; decidere se sostituirla o affiancarla spetta all'azienda. Non inventare una pubblicazione né creare siti duplicati.
- La richiesta che ha guidato questa versione: «migliora il software, fallo tuo; il software diventa NefroCenter WR (Work Resources); rifacciamo tutto, usa un altro layout, usa il tuo codice», conservando tutte le funzioni della 0.11, con guide, manuale, videoguide, documentazione, un unico ZIP, il sorgente in TXT e questo documento di passaggio.

## 3. Decisioni da conservare

- Tutte le funzioni della 0.11 restano (tabella in `gestionale/NOVITA_WR_1.0.md`). Il portale personale del dipendente **non** è nel perimetro.
- Approvazione mensile, promemoria, invio email e seconda copia NAS **arrivano spenti** nel portale aziendale; nei dati dimostrativi alcune strutture hanno l'approvazione attiva per mostrare il percorso.
- La seconda copia dei backup va su **NAS**: percorso e accesso li decide il tecnico; il portale rifiuta cartelle dentro i dati e collegamenti simbolici.
- Servizio di posta e gestionale paghe **non sono noti**: non attribuire compatibilità a fornitori inventati. La password SMTP vive solo nell'ambiente del servizio (`WR_SMTP_PASSWORD`).
- Il file Excel mensile **non si compila più**: il portale sostituisce ogni sua parte (studio completo in `gestionale/docs/STUDIO_MODELLO_EXCEL.md`). L'importazione del vecchio file serve per i mesi passati e la transizione; deve funzionare con i file compilati davvero dagli uffici (le celle non riconosciute si elencano, non bloccano). Il foglio «Collaboratori» importato è solo un promemoria; l'IBAN non viene mai copiato dal file.
- Nessun dato aziendale nei sorgenti, nelle schermate, nei video, nella demo o nelle prove: solo dati fittizi (`wr/sample.py`, `tests/`). Il file Excel reale usato per provare l'importazione non fa parte del progetto.
- Lingua: italiano semplice in interfaccia, documenti e messaggi del programma. Il codice ha nomi inglesi e commenti italiani.

## 4. Ruoli

| Ruolo | Ambito |
|---|---|
| Amministratore | tutto: strutture, parametri, accessi, backup, posta, promemoria, importazioni, oltre al lavoro HR |
| HR centrale | persone, fascicoli, documenti e verifiche, personale di gruppo, uscite, rubrica, accordi, paghe, comunicazioni, approvazione finale del mese, per tutte le strutture |
| Responsabile | strutture assegnate: presenze e pianificazione, controlli e chiusura, copertura e sostituzioni, persone, parametri |
| Compilatore | strutture assegnate: registra le presenze nei mesi aperti; orari, sede, festivo, pianificazione, eliminazione ed esportazione dipendono dai parametri della struttura |
| Direzione | sola consultazione delle strutture assegnate |

La tabella dei permessi è in `wr/permissions.py` ed è la stessa mostrata nella pagina «Ruoli e permessi». I controlli sono applicati dal server; l'interfaccia mostra solo ciò che è consentito.

## 5. Architettura e mappa dei sorgenti

Python 3.12/3.13 standard library + `cryptography` (Fernet per i segreti dell'app Authenticator) + `tzdata`; Waitress, XlsxWriter e Segno inclusi in `gestionale/vendor/`. SQLite in modalità WAL sul disco locale del server. Interfaccia in HTML, CSS e JavaScript (moduli ES, nessun framework, nessuna compilazione).

| Percorso (in `gestionale/`) | Responsabilità |
|---|---|
| `manage.py` | console: init, serve, check, backup, backup-config/status/sync/probe, activate, after-restore, migra-011, demo-data |
| `wr/app.py`, `wr/web.py`, `wr/server.py` | costruzione dell'applicazione, server WSGI (rotte, sessione, CSRF, CSP, file statici), avvio con Waitress e attività periodiche |
| `wr/db.py`, `wr/schema.py` | archivio SQLite, schema versionato, backup (snapshot), riconoscimento dell'archivio 0.11 |
| `wr/auth.py`, `wr/security.py`, `wr/users.py`, `wr/permissions.py` | password, TOTP, codici di recupero, attivazioni, conferma di sicurezza, account e ruoli |
| `wr/rules.py`, `wr/centers.py`, `wr/months.py`, `wr/attendance.py` | regole, parametri versionati delle strutture, stato del mese, registro presenze e pazienti per fascia |
| `wr/approvals.py`, `wr/agreements.py`, `wr/staffing.py` | approvazione mensile, accordi e calcoli, copertura e sostituzioni |
| `wr/people.py`, `wr/hr.py`, `wr/reviews.py`, `wr/workforce.py`, `wr/departures.py`, `wr/structures.py` | persone, fascicoli e inserimento, documenti e verifiche, personale di gruppo, uscite e dotazioni, rubrica |
| `wr/payroll.py`, `wr/analytics.py`, `wr/exports.py`, `wr/overview.py` | paghe, statistiche, esportazioni, riepilogo e «Da completare» |
| `wr/mail.py`, `wr/reminders.py`, `wr/backups.py` | comunicazioni e server di posta, promemoria, backup e seconda copia |
| `wr/collaborators.py`, `wr/model_export.py` | prospetto dei collaboratori a prestazione; foglio mensile nel formato del vecchio modello Excel |
| `wr/excel_import.py`, `wr/migrate011.py`, `wr/sample.py` | importazione del modello Excel (storico e transizione), migrazione dalla 0.11, dati fittizi |
| `web/index.html`, `web/js/app.js`, `web/js/pages/*.js`, `web/js/ui.js`, `web/js/help.js`, `web/css/wr.css` | interfaccia: avvio, menu e contesto, una pagina per modulo, helper, testi della guida, stile |
| `web/help/` | manuale illustrato e videoguide generati (si rigenerano con `strumenti/guide/`) |
| `tests/` | prove automatiche (`python3 -m unittest discover -s tests -p "test_*.py"`) |
| `strumenti/anteprima.py` | portale di prova con dati fittizi (`--aziendale` per accesso con password e Authenticator) |

Nella cartella `demo/`: `costruisci_demo.py` (crea `dist/`), `sorgenti/ponte.py` e `sorgenti/demo-main.js` (il motore nel browser con Pyodide), `avvia_demo.py`, `prova_demo.cjs`. In `strumenti/`: `giro_interfaccia.cjs` e `schermate.cjs` (prove Playwright), `archivio_011_di_prova.py` (archivio 0.11 sintetico per la migrazione), `guide/` (manuale e videoguide), `consegna.py`.

Convenzioni dell'interfaccia: nessuno stile o script in linea (CSP severa; i colori dinamici passano da `style.setProperty` su variabili CSS); i moduli di pagina esportano `render(ctx)` e ricevono `ctx = {app, params, query, go, refresh, setContext, reloadProfile}`; le pagine sono registrate in `PAGES` dentro `app.js`.

## 6. Avvio e prove

```bash
cd gestionale
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -p "test_*.py"      # prove automatiche
.venv/bin/python strumenti/anteprima.py --port 8090                  # portale di prova (dati fittizi, profili senza password)
.venv/bin/python strumenti/anteprima.py --port 8092 --aziendale      # come in azienda: password e Authenticator (dati fittizi)
```

Prove dell'interfaccia con Node.js e Playwright (Chromium): `node strumenti/giro_interfaccia.cjs CARTELLA http://127.0.0.1:8090` apre tutte le pagine di ogni profilo e raccoglie errori; `node strumenti/schermate.cjs CARTELLA` fa le schermate. Nei contenitori senza sandbox serve `QA_CHROMIUM_NO_SANDBOX=1`. Demo: `cd demo && python3 costruisci_demo.py && python3 avvia_demo.py --port 8095`, poi `node prova_demo.cjs CARTELLA http://127.0.0.1:8095`.

`manage.py init` crea una **nuova** installazione e rifiuta un archivio esistente. Non eseguirlo per ispezionare o aggiornare un archivio: usare `check`. `after-restore` non è in sola lettura. Per il portale aziendale seguire `gestionale/INSTALLAZIONE_PASSO_PASSO.md` (dettagliata) o `gestionale/INSTALLAZIONE.md` (riferimento).

## 7. Verifiche eseguite e limiti

Il dettaglio aggiornato è in `gestionale/VERIFICA.md` e `gestionale/STATO_PROGETTO.json`. In sintesi: prove automatiche del motore (compresi migrazione e importazione Excel), giro completo dell'interfaccia per i cinque profili senza errori, controllo su telefono, demo provata nel browser con Pyodide (locale e da rete di distribuzione), importazione provata sul modello Excel reale di un mese (fuori dai sorgenti), manuale e videoguide generati dalle schermate del portale di prova e controllati.

Non sono stati collaudati: server aziendale e rete reale, carico reale delle sedi, NAS, servizio di posta, tracciato del consulente, migrazione di un archivio aziendale reale (solo archivi sintetici). Il collaudo in un contenitore Linux non sostituisce quello sul server dell'azienda.

## 8. Guide

- Guida in linea: `web/js/help.js` (testi per pagina e per ruolo) e `web/js/pages/guide.js` (procedure, domande frequenti, scheda «Manuale e video»). Modificare qui i testi: il manuale li rilegge da questi file.
- Manuale illustrato (HTML autonomo + PDF) e videoguide (MP4 senza audio con sottotitoli impressi, VTT, trascrizioni, copertine): in `web/help/`, generati da `strumenti/guide/manuale.cjs` e `strumenti/guide/video.cjs` con il portale di prova in modalità aziendale (dati fittizi). Rigenerarli dopo ogni cambiamento dell'interfaccia, non ritoccare i file prodotti a mano.

## 9. Come continuare

1. Leggere `CLAUDE.md`, questo documento, `gestionale/VERIFICA.md` e `gestionale/STATO_PROGETTO.json`; controllare lo stato di Git e conservare le modifiche presenti.
2. Ogni cambiamento al motore passa dalle prove (`tests/`); ogni cambiamento all'interfaccia dal giro Playwright dei cinque profili e, se cambia una pagina documentata, dalla rigenerazione di manuale e video.
3. Mai `init` su dati esistenti; mai attivare posta, promemoria o NAS con destinazioni presunte; mai dati reali in sorgenti, prove, schermate, demo.
4. Per una messa in esercizio restano da concordare con l'azienda: server e HTTPS, account nominativi, cartella NAS e prova di ripristino, servizio di posta e mittente, specifica del consulente paghe e prova con un mese pilota, flusso operativo con HR, eventuale migrazione dalla 0.11 su una copia dell'archivio.
5. Riportare sempre, in italiano semplice: cosa è stato modificato, quali controlli sono stati davvero eseguiti e cosa resta da completare.
