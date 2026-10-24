# Ripetere il collaudo

I test utilizzano dati fittizi e creano database, chiavi e account temporanei. Non richiedono credenziali reali. Eseguirli in una copia di sviluppo del progetto, con le dipendenze Python installate secondo `INSTALLAZIONE_WEB.md`.

## Test della logica e del servizio

Dalla directory del progetto:

```bash
python -m unittest discover -v
```

La suite comprende le prove della 0.11 e le regressioni precedenti. Conteggi ed esiti effettivi sono in `../VERIFICA.md`; i rapporti JSON dell’edizione qualità sono inclusi in questa cartella. I log temporanei di sviluppo sono esclusi dal pacchetto. Le sezioni successive conservano anche il contesto storico dei collaudi.

## Percorsi nel browser

Il collaudo richiede separatamente Node.js, Playwright e Chromium. Sono strumenti di sviluppo, non dipendenze necessarie al funzionamento dell’app. Ambiente utilizzato: Node.js 24.19.0 e Playwright 1.62.1 su Linux.

Se non già disponibili, in una copia di sviluppo:

```bash
npm install --no-save playwright@1.62.1
npx playwright install chromium
python qa/run_browser.py
```

Il comando avvia Waitress su una porta loopback libera, esegue il percorso reale di attivazione 2FA e crea persone, allegati e presenze dimostrative. Controlla anche le modifiche concorrenti e i quattro stili a diverse larghezze. Alla fine arresta il server ed elimina l’archivio temporaneo. Le immagini vengono scritte in `qa-output/`.

Variabili facoltative:

| Variabile | Uso |
|---|---|
| `NODE_BINARY` | Percorso dell’interprete Node.js, se non presente nel PATH |
| `CHROMIUM_EXECUTABLE` | Browser Chromium già installato da utilizzare per la prova |
| `QA_OUTPUT_DIR` | Directory in cui scrivere immagini e download dimostrativi del collaudo |
| `QA_CHROMIUM_NO_SANDBOX=1` | Solo per un contenitore di test isolato che richiede Chromium senza sandbox |

`browser-tests.log` conserva l’esito della prova inclusa nella consegna. Le password presenti nello script appartengono esclusivamente al database temporaneo: l’app operativa non crea account o password predefiniti.

L’anteprima mostrata in conversazione è un prototipo separato con dati fittizi e 2FA simulata. `history/v0.7-preview-tests.log` documenta la prova delle sue quattro varianti; non è il test dell’autenticazione reale, che è coperta dalla suite Python e dal percorso browser qui descritto.

Nella 0.8 il percorso controlla anche statistiche, filtri centro/ruolo/persona, dati mancanti, i sei download Excel e il backup scaricato. Il confronto delle celle XLSX nei test Python usa direttamente OOXML e non richiede Excel o librerie di lettura aggiuntive. Le prove della fonte Excel della 0.7 sono conservate come storico; la 0.8 non include la fonte originale.

## Regressioni della 0.8.1

Le nuove prove Python coprono tipi numerici dei fascicoli Excel, falsi candidati al backup giornaliero e procedura console `after-restore`. Il percorso browser verifica inoltre campi mese nascosti nelle esportazioni, filtro ruolo e selezione HR dopo il cambio di centro. Le immagini del nuovo confronto stili sono generate dallo stesso percorso.

Ambiente del collaudo 0.8.1: Python 3.12.14, cryptography 50.0.2, Node.js 24.19.0, Playwright 1.62.1 e Chromium 154.0.8037.57 di sistema. Esempio per questo contenitore Linux isolato:

```bash
CHROMIUM_EXECUTABLE=/usr/bin/chromium QA_CHROMIUM_NO_SANDBOX=1 python qa/run_browser.py
```

Usare l’opzione senza sandbox soltanto dove necessaria nel contenitore di test. Il browser di produzione dell’utente non richiede questa configurazione. I download generati dalla prova contengono esclusivamente dati fittizi e non sono inclusi nel pacchetto di consegna.

## Collaudo 0.9

`browser.cjs` esegue anche `v09_ui.cjs`: attività, decorrenze contrattuali, protezione delle modifiche non salvate durante l’aiuto, PDF centrali, passaggio fra centri, paghe in bozza, NAS disattivato, guide e video, tutorial e ruolo HR in sola lettura sulle presenze. Tutto il percorso è passato nell’ambiente descritto sopra. Per la demo statica, il relativo pacchetto contiene `demo-browser-check.cjs` e le istruzioni; l’esito è conservato anche qui in `demo-browser-tests.log`.


## Collaudo 0.10

`test_structures.py` controlla la rubrica condivisa, permessi aggiornati, isolamento dei centri, validazione e conflitti di salvataggio. `test_communications.py` verifica modelli e variabili, liste, deduplicazione, bozze immutabili, limiti orari, TLS, destinatari individuali, conferme obsolete o ripetute e concorrenza. Il trasporto SMTP è simulato: questi test non spediscono email reali. `test_web_v010.py` controlla le API e la procedura di ripristino che disabilita SMTP e sospende gli invii pendenti.

Per ripetere solo le nuove prove Python:

```bash
python -m unittest test_structures test_communications test_web_v010 -v
```

`browser.cjs` esegue anche `v010_ui.cjs`: rubrica e sezione Struttura del fascicolo, liste e modelli, anteprima, bozza con invio disattivato, aiuto contestuale e pagine a 390/320 px. La demo statica aggiunge la simulazione esplicita di un invio, senza rete SMTP. Gli esiti finali aggiornati sono documentati in `../VERIFICA.md`.

## Collaudo 0.11

`test_approvals.py`, `test_document_reviews.py`, `test_departures.py`, `test_reminders.py`, `test_staffing.py`, `test_payroll_connector.py` e `test_web_v011.py` coprono nuovi flussi, permessi e concorrenza. `qa/v011_ui.cjs` verifica le operazioni nel browser, le finestre e il mobile; i controlli SMTP usano simulazioni. `unit-v011-tests.log` e `browser-v011.log` riportano gli esiti della versione. La demo include inoltre `v011-check.cjs`, che prova i sei percorsi senza accesso alla rete.

## Edizione qualità 0.11.1

Per ripetere i controlli mirati degli asset e delle API:

```bash
python -m unittest test_web_v09 test_web_v011 -v
```

Il rapporto riepilogativo è `media-quality-verification.json`. Il pacchetto demo separato include `help-quality-check.cjs`, `presentation-check.cjs`, `demo-browser-check.cjs`, `roles-check.cjs`, `v011-check.cjs` e `test_demo_server.py`. Per i test browser avviare la demo con `python avvia_demo.py --port 8765`, così il server gestisce le richieste Range dei video.

Guide e media si rigenerano seguendo `README_GUIDE_VIDEO.md`, `MANUALI_ILLUSTRATI.md` e `presentation_quality/README.md`. Le prove dei rendering sono distinte dalla semplice compilazione dei sorgenti.
