# Passaggio a Claude Code — NefroCenter

Stato al **24 ottobre 2026**. Edizione della consegna **0.11.1**, versione funzionale del backend **0.11**, schema database **8**.

Questo documento raccoglie il contesto tecnico del progetto e le decisioni già espresse dall’utente. Non contiene credenziali e non autorizza nuove installazioni aziendali, invii reali, cancellazioni o cambi di pubblico. La richiesta corrente dell’utente determina il lavoro da svolgere. Verificare i file e l’ambiente effettivamente disponibili prima di modificare il progetto.

## 1. Come consegnare il progetto a Claude Code

Il solo documento di passaggio non contiene il programma. Occorre accompagnarlo con il TXT dei sorgenti oppure con gli ZIP.

**Percorso consigliato con il TXT:** scaricare integralmente `Codice_Sorgente_NefroCenter_v0.11.1.txt` e, con Python 3.12 o superiore, eseguire dalla cartella che lo contiene:

```bash
python Codice_Sorgente_NefroCenter_v0.11.1.txt --directory NefroCenter_Sorgenti
```

Il comando verifica le impronte SHA-256 e crea una cartella nuova con:

```text
NefroCenter_Sorgenti/
  gestionale/     # applicazione Python, frontend, guide e strumenti
    CLAUDE.md    # copia di questo documento
  demo/          # demo statica, dati sintetici e launcher locale
```

Non installa dipendenze, non avvia servizi e rifiuta una destinazione già popolata. Il TXT è anche codice Python leggibile: `TEXT_FILES` contiene sorgenti e documenti, `BINARY_FILES` e `BINARY_CONTENTS` ricostruiscono le risorse binarie deduplicate. È grande perché include anche i media: un download completo evita copie parziali.

**Alternativa con ZIP:** estrarre `NefroCenter_Presenze_Web_v0.11.1.zip` e `NefroCenter_Demo_v0.11.1.zip` in cartelle separate. Il primo contiene la cartella `Presenze_Web_v0.11.1/`, il secondo `NefroCenter_Demo/`. Conservare le rispettive strutture interne. Le vecchie copie di rollback sono nel pacchetto del gestionale; non sono nel TXT.

Aprire Claude Code nella cartella comune ricostruita, oppure nella cartella del gestionale, e indicargli:

> Leggi `gestionale/CLAUDE.md` (oppure `CLAUDE.md` se sei già nel gestionale), poi `STATO_PROGETTO.json` e `VERIFICA.md`. Verifica quali file e strumenti sono presenti. Conserva il lavoro esistente e prosegui con la mia richiesta, distinguendo demo pubblica e applicazione aziendale.

I percorsi di lavorazione precedenti erano `/workspace/nefrocenter/Presenze_Web_v0.8`, `/workspace/sites/nefrocenter-demo` e `/workspace/consegna`. Il nome storico `v0.8` della prima cartella **non indica la versione corrente**. Questi percorsi potrebbero non esistere sul computer che esegue Claude: usare le cartelle appena estratte o ricostruite.

## 2. Obiettivo e stato effettivo

NefroCenter — Persone e Presenze è un portale centrale per presenze, fascicoli del personale, documenti HR, strutture, comunicazioni e processi amministrativi. Nell’installazione operativa le sedi usano il browser e lo stesso archivio centrale; HR può vedere e verificare i documenti caricati dalle sedi remote.

La **demo pubblica è online e aggiornata**:

https://nefrocenter-demo.icy-bass-2671.chatgpt.site

La demo contiene tre centri, dodici anagrafiche fittizie e cinque profili senza password. Ogni visitatore lavora su una propria copia in `sessionStorage`; le modifiche non vengono condivise fra persone. Il cambio di ruolo nella stessa scheda permette di provare il passaggio sede → HR. Gli invii email sono simulati. I file Excel di esempio rappresentano il campione iniziale; statistiche e CSV del registro possono riflettere le modifiche della sessione.

Il **gestionale operativo non è installato su un server aziendale**. Non confondere la pubblicazione della demo con l’attivazione dell’archivio HR reale, di SMTP, del NAS o delle integrazioni paghe.

La revisione 0.11.1 migliora guide, video, materiali HR e la demo locale; `/health` continua a riportare 0.11 e il database resta allo schema 8.

## 3. Funzioni e decisioni da preservare

Sono presenti registro delle presenze e pianificazione, fascicoli e onboarding, documenti e scadenze, identità e decorrenze di gruppo, accordi e calcoli, statistiche/esportazioni, backup e seconda copia su NAS, rubrica strutture, modelli email, liste di destinatari, anteprime e bozze. Il fascicolo collega il dipendente alla struttura di riferimento e ai suoi recapiti.

Le sei aggiunte approvate e implementate nella versione 0.11 sono:

| Funzione | Comportamento da conservare |
|---|---|
| Approvazione mensile | Invio della sede, verifica del responsabile, approvazione HR; restituzione con nota e blocco delle modifiche dopo l’invio. Versione e impronta proteggono la verifica. |
| Verifica documenti | HR conferma o richiede correzioni; la sede ripresenta il documento. Storico delle decisioni; verifica e scadenza restano concetti distinti. |
| Promemoria | Riepiloghi configurabili, deduplicazione e anteprima; automazione inizialmente disattivata. Nessun invio reale durante lo sviluppo. |
| Specifiche paghe | Importazione di intestazioni o specifiche JSON, mappatura e controlli. Profilo generico in bozza finché non è noto il tracciato del consulente. Non produce cedolini. |
| Copertura e sostituzioni | Confronto con fabbisogni, disponibilità e turni; sostituzioni fra identità collegate, con verifica dei conflitti e accettazione della sede destinataria. |
| Uscite e dotazioni | Checklist e consegna/restituzione delle dotazioni; chiusura consentita dopo le attività richieste. Non modifica automaticamente anagrafiche, contratti o account esterni. |

Decisioni dell’utente già raccolte:

- La seconda copia dei backup deve andare su **NAS**; percorso e accesso effettivi non sono ancora definiti.
- Servizio di posta aziendale e gestionale/tracciato paghe **non sono ancora noti**. Non attribuire una compatibilità a un fornitore inventato.
- Guide per pagine e impostazioni, videoguide, spiegazione dei ruoli, presentazione HR, video con audio, file di installazione e sorgenti in TXT fanno parte della consegna.
- Il portale personale del dipendente non è stato incluso nel perimetro approvato.

SMTP, promemoria e copia NAS richiedono configurazione reale. Le approvazioni sono inizialmente disattivate nel gestionale operativo e attive nei dati dimostrativi per mostrare il percorso. Un’accettazione SMTP non equivale a conferma di consegna al destinatario.

## 4. Ruoli

| Ruolo | Ambito e capacità principali | Limiti principali |
|---|---|---|
| Amministratore | Tutti i centri; utenti, ruoli, configurazioni, HR, approvazioni, SMTP, promemoria e backup. | Profilo tecnico con i permessi più estesi. |
| HR centrale | Fascicoli e documenti di tutti i centri, verifiche documentali, approvazione finale del mese, dati di gruppo, paghe e comunicazioni. | Non modifica direttamente presenze o parametri; non amministra utenti, backup, SMTP o programmazione dei promemoria. |
| Responsabile | Centri assegnati; presenze, parametri, fascicoli, verifica del mese, copertura e attività autorizzate della sede. | Non dà l’approvazione finale HR, non valida documenti e non configura approvazioni, account, posta o backup. |
| Compilatore | Centri assegnati; presenze nei mesi aperti, operazioni consentite dai parametri e invio del mese al responsabile. | Non accede a fascicoli, documenti HR, accordi economici, paghe o comunicazioni; non chiude il mese. |
| Direzione / lettore | Consultazione di presenze, dashboard, riepiloghi, statistiche e prospetti consentiti nei centri assegnati. | Non modifica dati e non accede ai fascicoli o alle informazioni economiche riservate. |

I controlli effettivi stanno nel backend; la demo replica i confini dei ruoli con un adattatore locale. Se si cambia un permesso, controllare entrambi e le descrizioni della pagina iniziale. La scelta di un percorso nella Guida non modifica i permessi dell’account.

## 5. Architettura e mappa dei sorgenti

Backend Python con Waitress; database SQLite in modalità WAL su **disco locale di un server applicativo centrale**. HTML, CSS e JavaScript senza un framework frontend da compilare. Le dipendenze esterne correnti sono fissate in `requirements.txt` (`cryptography==50.0.2`, `tzdata==2026.5`); altri componenti sono distribuiti nel progetto con le rispettive licenze.

| Percorso relativo al gestionale | Responsabilità |
|---|---|
| `web_server.py`, `web_auth.py`, `manage.py` | HTTP, sessioni/2FA e amministrazione da console. |
| `core.py`, `engine.py`, `rules.py` | Archivio, inizializzazione/schema e logica delle presenze. |
| `hr.py`, `tasks.py`, `workforce.py` | Fascicoli, attività, identità e decorrenze del personale. |
| `approvals.py`, `document_reviews.py` | Approvazioni mensili e verifiche documentali. |
| `staffing.py`, `departures.py`, `reminders.py` | Coperture, uscite/dotazioni e promemoria. |
| `structures.py`, `communications.py` | Strutture, modelli, liste, bozze e trasporto SMTP. |
| `payroll.py`, `agreements.py` | Preparazione paghe e accordi/calcoli. |
| `analytics.py`, `excel_exports.py` | Statistiche ed esportazioni. |
| `backup_policy.py`, `backup_tools.py` | Backup, seconda copia e prove tecniche di ripristino. |
| `ui.html`, `assets/` | Interfaccia operativa, componenti delle pagine e media della Guida. |
| `docs/help_quality.json`, `docs/help_v011_*.json` | Contenuti editoriali della Guida. |
| `qa/generate_guides.py` | Generazione del catalogo, del manuale Markdown e dei dati JavaScript. |
| `deploy/`, `INSTALLAZIONE_WEB.md` | Esempi di servizio e reverse proxy; installazione da adattare all’azienda. |
| `test_*.py`, `qa/` | Test applicativi, browser, strumenti media e rapporti di verifica. |

Nella **cartella demo**, `dist/` è la radice pubblicabile. `dist/demo.js` adatta le API a dati fittizi e gestisce ruoli e presentazione; `dist/demo_seed.json` contiene il campione. `avvia_demo.py` serve esclusivamente `dist/` e supporta richieste Range per saltare ai capitoli MP4. Non sostituirlo con un server statico privo di Range se occorre mantenere quel comportamento.

Le risorse frontend del gestionale vengono copiate nella demo: dopo una modifica condivisa verificare che `gestionale/assets/` e `demo/dist/assets/` siano allineati, senza copiare database, chiavi o cartelle operative.

## 6. Avvio e test

### Demo locale senza dati aziendali

Dalla cartella della demo:

```bash
python avvia_demo.py --port 8765
```

Aprire `http://127.0.0.1:8765`. È sufficiente Python; non servono account reali. L’opzione `--lan` consente la prova sulla rete locale e va usata nel contesto di rete scelto dall’utente.

### Gestionale: preparazione di sviluppo

Dalla cartella del gestionale, su Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest test_web_v09 test_web_v011 -v
```

Su Windows l’interprete equivalente è `.venv\Scripts\python.exe`. Per una prova completa della logica: `python -m unittest discover -v`, usando l’interprete dell’ambiente virtuale.

`manage.py init` serve **solo a creare una nuova installazione** e richiede dati e password da console. Non eseguirlo per ispezionare o aggiornare un archivio esistente. Per un’installazione nuova o una prova manuale seguire `INSTALLAZIONE_IN_BREVE.md` e `INSTALLAZIONE_WEB.md`; non sono incluse credenziali operative predefinite.

Con un archivio di sviluppo già inizializzato e la sua chiave, il comando locale previsto è:

```bash
.venv/bin/python web_server.py --data-dir data --key-file private/server.key --origin http://127.0.0.1:8080 --dev-http
```

`--dev-http` è limitato al loopback. L’uso aziendale richiede HTTPS e reverse proxy; la porta applicativa 8080 resta interna.

### Browser

Servono Node.js, Playwright e Chromium, separati dalle dipendenze necessarie agli utenti del portale. `qa/run_browser.py` crea un archivio e account fittizi temporanei, prova attivazione 2FA e flussi e li elimina alla fine:

```bash
python qa/run_browser.py
```

`CHROMIUM_EXECUTABLE` può indicare un Chromium già installato. `QA_CHROMIUM_NO_SANDBOX=1` è stato usato nel contenitore isolato del collaudo; non è un’impostazione da imporre normalmente sui computer degli utenti. I dettagli sono in `qa/README.md`.

Con il launcher demo attivo sulla porta 8765, dalla cartella demo:

```bash
python -m unittest test_demo_server -v
node demo-check.cjs
node v011-check.cjs
node demo-browser-check.cjs
node roles-check.cjs
node help-quality-check.cjs
node presentation-check.cjs
```

Le prove browser richiedono Playwright e il browser configurato. Gli script non dimostrano la disponibilità di servizi aziendali esterni.

## 7. Verifiche già eseguite e limiti

La suite completa di base della 0.11 aveva superato **254 test Python**. Nella revisione qualità sono stati verificati **10 test HTTP applicativi**, **4 test del server demo** e i percorsi browser del gestionale e dei cinque ruoli della demo. Il numero 254 è un risultato storico della suite di base, non una nuova esecuzione completa della 0.11.1.

Sono passati ricerca e navigazione della Guida, sette percorsi ordinati, 34 procedure e 323 impostazioni, immagini e PDF, sottotitoli e salto diretto ai capitoli prima della riproduzione, conservazione delle modifiche HR non salvate, desktop e mobile a 390/320 px. Il responsabile non può configurare le approvazioni: la regressione verifica risposta 403 e configurazione invariata.

Rapporti inclusi:

- `VERIFICA.md` e `STATO_PROGETTO.json`: esiti, versione e stato di pubblicazione.
- `qa/media-quality-verification.json`: prove applicative e browser dell’edizione qualità.
- `qa/guide_quality_validation.json`: 34 video e 46 schermate portabili.
- `qa/manual-delivery-validation.json`, `qa/manual-pdf-validation.json`: manuali e PDF.
- `qa/presentation_quality/verification.json`: presentazione e impronte dei file verificati.
- `VERIFICA_PACCHETTO_v0.11.1.txt` e `SHA256SUMS_v0.11.1.txt` nella consegna: controllo effettivo di TXT ricostruito, ZIP e file consegnati.

Non sono stati collaudati server Windows aziendali, rete reale, carico reale delle sedi, NAS, SMTP o tracciato del consulente. Non dichiarare impossibile una configurazione solo perché manca uno strumento nel PATH; cercare le alternative disponibili e distinguere ciò che manca da ciò che non è stato verificato.

## 8. Guide e presentazione

Materiali aggiornati nella consegna:

- `Guida_NefroCenter_v0.11_illustrata.pdf` e `.html`: **42 pagine**, 34 procedure, percorsi per ruolo, prerequisiti, esempi, problemi frequenti e schermate.
- `Presentazione_HR_NefroCenter_v0.11_illustrata.pdf` e `.html`: **11 pagine** per la presentazione all’ufficio HR.
- `Riferimento_Impostazioni_NefroCenter_v0.11.html`: **323 impostazioni**, ricerca e filtri.
- `Presentazione_NefroCenter_v0.11_qualita_con_audio.mp4`: **157 secondi**, Full HD 1920×1080 a 30 fps, voce sintetica italiana, 11 capitoli e 40 sottotitoli; disponibile anche senza audio, con VTT, trascrizione e sola voce MP3.
- `assets/guides/`: **34 videoguide illustrate senza audio**, Full HD a 30 fps, con copertine, capitoli, sottotitoli e trascrizioni. Sono istruzioni illustrate con schermate di riferimento, non registrazioni di operazioni dal vivo.

Il manuale del portale è `assets/guida_illustrata.pdf`. Nella demo i materiali generali sono in `dist/presentation/`. I nomi dei media conservano `v0.11` anche nella consegna qualità 0.11.1.

Per modificare i contenuti, aggiornare le fonti e rigenerare gli output; evitare correzioni isolate ai soli file generati. Dalla cartella del gestionale:

```bash
python qa/generate_guides.py
```

Per un singolo video, con Pillow, FFmpeg/ffprobe e font richiesti installati:

```bash
python qa/generate_guides.py --videos --only-topic copertura
python qa/validate_guide_media.py
```

Istruzioni di rigenerazione complete: `qa/README_GUIDE_VIDEO.md`, `qa/MANUALI_ILLUSTRATI.md`, `qa/presentation_quality/README.md`. Le 46 schermate sintetiche sono in `assets/guide_screens/` con manifest relativo. I sorgenti della presentazione includono scene, audio già sintetizzato e schermate: il montaggio originale si può ricostruire senza una nuova richiesta vocale; cambiare la narrazione richiede nuova sintesi e rete autorizzata. Gli strumenti media sono dipendenze di sviluppo, non requisiti per usare il gestionale.

## 9. Pubblicazione della demo

Pubblicazione verificata con esito **succeeded**, versione Sites **6**, il 24 ottobre 2026. Conservare lo stesso sito e il pubblico già scelto dall’utente.

| Riferimento | Valore |
|---|---|
| URL | `https://nefrocenter-demo.icy-bass-2671.chatgpt.site` |
| Progetto Sites | `appgprj_6ad5c746ebc0819197ed58cba06b6f4d` |
| Commit sorgente pubblicato | `19461f4da82c382fdb97d64d26dcc63342c3c3e4` |
| Versione salvata | `appgprj_6ad5c746ebc0819197ed58cba06b6f4d~appgver_48f926e5d0f4819193e910ca14d9871f` |
| Deployment | `appgdep_6adbf84733108191883ad9ccf8c80cc0` |

Gli ZIP/TXT sono distribuzioni portabili: non includono cronologia Git, credenziali o configurazione privata di accesso a Sites. La presenza di questi identificativi non conferisce accesso al servizio. Claude Code può modificare e provare la demo locale; per pubblicare sullo stesso indirizzo deve disporre di un collegamento e di credenziali autorizzati. Non inventare una pubblicazione riuscita né creare un sito duplicato per sostituire un accesso mancante.

Nel trasferimento precedente il repository remoto ha rifiutato un unico push molto grande. I sorgenti sono stati caricati in blocchi più piccoli, quindi è stato verificato che l’albero finale coincidesse con quello collaudato; la versione pubblicata usa quell’albero finale. Si tratta di un limite di trasferimento osservato, non di un difetto del software o di una ragione per ridurre la qualità dei media.

## 10. Continuazione e tutela del lavoro esistente

Prima di intervenire leggere `AGGIORNAMENTO_0.11.1.md`, `AGGIORNAMENTO_0.11.md`, `STATO_PROGETTO.json` e `VERIFICA.md`. Controllare lo stato locale e conservare eventuali modifiche già presenti. I documenti storici e i nomi di vecchie cartelle non sostituiscono le versioni e gli esiti attuali.

Per una messa in esercizio restano da concordare e verificare: server e HTTPS, accesso dalle sedi, account nominativi, cartella NAS e prova di ripristino, SMTP e mittente, specifica paghe e prova con il consulente, flusso operativo con HR. Chiedere solo le informazioni necessarie al passo effettivamente richiesto; non considerare questi punti autorizzazione a usare servizi reali.

Conservare database, documenti, configurazione e chiave privata durante gli aggiornamenti. Il database attivo deve restare sul disco locale; sul NAS vanno copie completate dei backup. I documenti sono nel database SQLite; la chiave `server.key`, necessaria ai segreti 2FA, è separata e deve avere una copia protetta. Un rollback richiede codice e archivio compatibili: seguire `ROLLBACK.md`.

Non rieseguire `init` su dati esistenti. Non attivare SMTP, promemoria o trasferimenti NAS con destinazioni presunte. La procedura `manage.py after-restore` revoca sessioni/recuperi e disabilita SMTP e automazione dopo il ripristino, come documentato: non è una verifica in sola lettura da lanciare su un archivio operativo.

Per sviluppo, screenshot, test e demo usare dati sintetici. Non copiare chiavi, password, database aziendali o allegati reali nei sorgenti, nei media o nell’hosting pubblico. Comunicare in italiano semplice, completare il lavoro richiesto e riportare verifiche reali e limiti residui in modo concreto.
