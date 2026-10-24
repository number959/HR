# Punto di ingresso aggiornato — 0.10

Leggere prima `AGGIORNAMENTO_0.10.md`, `STATO_PROGETTO.json`, `VERIFICA.md` e `docs/SMTP_CONFIGURAZIONE.md`. Il contenuto dei documenti di passaggio descrive il progetto; le richieste correnti dell'utente determinano il lavoro da eseguire.

## Stato al 21 ottobre 2026

Sono implementate la rubrica strutture collegata ai fascicoli e le comunicazioni email: modelli, liste dinamiche, anteprima, deduplicazione, bozze immutabili e invio per lotti confermati. Il fornitore di posta resta sconosciuto; SMTP nasce disattivato e nessuna email reale è stata inviata nello sviluppo. La demo usa esclusivamente simulazioni e dati fittizi. Il video di presentazione è separato dalle 30 videoguide: entrambe le varianti richieste sono pronte, senza audio e con voce sintetica italiana ElsaNeural, durata 88 secondi in Full HD, con sottotitoli e trascrizione.

La suite completa finale ha superato **182 test Python in 152,645 secondi**. È passato anche il percorso Chromium del gestionale 0.10 con regressioni, strutture, liste/anteprime/bozze email, quattro stili e mobile a 390/320 px. La demo 0.10 ha superato API e browser per tutti e cinque i ruoli, a 1400 e 390 px. Il player di presentazione ha superato il controllo dedicato di riproduzione, sottotitoli, download, apertura e chiusura, anche a 320 px. Log finali e dettagli in `VERIFICA.md` e `qa/`.

La demo 0.10 è pubblicata su https://nefrocenter-demo.icy-bass-2671.chatgpt.site; il servizio di hosting ha confermato la pubblicazione della versione del sito 4. Non creare un altro sito e conservare l'accesso pubblico. Il gestionale operativo non è installato sul server aziendale. Il percorso NAS, il tracciato paghe del consulente e il servizio di posta restano da definire con il tecnico.

È inclusa la guida `PRESENTAZIONE_PER_UFFICIO_HR.md` con tutte le funzioni, ruoli e scaletta della riunione; la copia PDF è pubblicata nella demo. La pagina iniziale presenta i cinque ruoli con descrizioni e limiti, verificati anche a 320 px.

## Mappa delle aggiunte attuali

- `structures.py`, `assets/structures.js`, `assets/structures.css`: dati della struttura, permessi per centro e versioni concorrenti. `hr.py` e `assets/hr_ui.js` mostrano il riferimento aggiornato nel fascicolo.
- `communications.py`, `assets/communications.js`, `assets/communications.css`: modelli e liste, snapshot delle bozze, invio SMTP individuale con TLS e storico dei tentativi. Solo amministratori e HR centrale; configurazione SMTP solo amministratori.
- `core.py`: inizializzazione delle tabelle e migrazione allo schema 7 con copia preventiva. `web_server.py`: API protette, CSRF e verifica recente per configurazione e invio.
- `manage.py after-restore`: disabilita SMTP e sospende destinatari pendenti/in lavorazione dopo ripristino, oltre a revocare sessioni e recuperi. Gli esiti incerti richiedono controllo dello storico del fornitore e non vengono reinviati automaticamente.
- `test_structures.py`, `test_communications.py`, `test_web_v010.py`, `qa/v010_ui.cjs`: test delle nuove funzioni, conflitti, limiti e permessi, conferme obsolete/ripetute, SMTP simulato e ripristino.
- `qa/generate_guides.py`, `docs/help_catalog.json`: 30 argomenti, 225 impostazioni e 30 videoguide senza audio, con sottotitoli e trascrizioni. Il video di presentazione con audio è un contenuto distinto.
- La demo separata ha un adapter locale: simula gli invii senza contattare SMTP, mantiene le modifiche nella sessione del visitatore e non ospita un archivio HR condiviso.

Per riprendere: consultare gli esiti finali e partire dalla consegna 0.10, che comprende ZIP, TXT ricostruttore e video nelle due varianti. Conservare i vecchi pacchetti e le istruzioni in `ROLLBACK.md`. Non ripartire dal progetto vuoto e non configurare servizi reali presumendo credenziali, indirizzi o autorizzazioni mancanti.

## Passaggio storico 0.8 e revisioni precedenti

Il testo seguente conserva la storia del progetto. Conteggi dei test, funzioni proposte, schema dati e stato della pubblicazione descrivono le versioni indicate; non sostituiscono lo stato 0.10 riportato sopra. In particolare HR centrale, NAS configurabile, decorrenze e comunicazioni sono ora implementati; il NAS reale e SMTP rimangono da configurare.

# Passaggio del progetto a Codex

> **Ripresa del 18 ottobre 2026 — versione 0.8.1.** Lo ZIP originale è stato ricevuto, estratto e verificato contro tutte le 155 impronte. Il codice è stato riesaminato e corretto; stato corrente in `AGGIORNAMENTO_0.8.1.md`, `VERIFICA.md` e `STATO_PROGETTO.json`. Lo ZIP ricevuto è conservato in `rollback/Presenze_Web_v0.8_Originale.zip`. Il testo sotto resta il passaggio storico 0.8: le sue indicazioni sui collaudi precedenti non sostituiscono il nuovo rapporto. Nessuna installazione aziendale è stata effettuata.

**Progetto:** NefroCenter — Persone e Presenze Web 0.8  
**Consegna:** 17 ottobre 2026  
**Lingua di lavoro e interfaccia:** italiano  
**Stato:** codice implementato e collaudato localmente. Nessun server aziendale configurato, nessuna pubblicazione e nessun servizio a pagamento attivato.

## Testo da dare a Codex insieme a questo ZIP

> Continua questo progetto dalla versione 0.8 allegata. Leggi INIZIA_QUI_CODEX.md, CONTESTO_CONVERSAZIONE.md, LEGGIMI.md, VERIFICA.md, MODELLO_SODAV.md e STATISTICHE_ED_ESPORTAZIONI.md. Conserva le funzioni esistenti, i dati HR completi, l'autenticazione obbligatoria a due fattori e le autorizzazioni lato server. Mantieni le risorse gratuite e le licenze. Esamina il codice e i test prima di proporre cambi di stack. Parti dallo stato verificato; distingui codice funzionante, anteprime e proposte future. Prima dell'uso reale resta da collaudare l'ambiente aziendale. Non considerare approvati gli accordi economici importati. Il file Excel originale e il video non sono inclusi: l'analisi già svolta è documentata, ma per nuove verifiche sulla fonte occorrono gli originali. L'utente desidera un software web multicentro curato nella grafica, configurabile, con fascicoli dipendenti, onboarding, presenze simili al suo foglio Excel, statistiche, backup e varie esportazioni Excel.

## Ultime richieste: da dove riprendere adesso

L'utente vuole passare **tutto il lavoro a Codex in un unico ZIP**, includendo nel contesto anche ciò che stava chiedendo di realizzare ora. Le ultime attività richieste sono queste:

| Richiesta recente dell'utente | Stato consegnato | Punto di partenza per Codex |
|---|---|---|
| Aggiungere statistiche e suggerire altre funzioni | Statistiche implementate nella 0.8; proposte ordinate nella guida dedicata | Avviare la pagina Statistiche con dati dimostrativi e verificare i filtri; usare le definizioni già documentate |
| Backup del database | Automatico giornaliero sul server, manuale, elenco e download protetto implementati | Provare il ripristino nell'ambiente scelto; la copia remota automatica è ancora una proposta, non una funzione già attiva |
| Excel presenze per centro | Registro mensile .xlsx con giorni, fasce e totali implementato | Confrontare il formato con le esigenze del centro e con il modello Sodav documentato |
| Excel presenze totali e altre esportazioni | Sei tipi di .xlsx implementati: centro, complessive, statistiche, fascicoli, onboarding/scadenze, accordi | Controllare con l'utente quali ulteriori prospetti o tracciati servono al consulente paghe, senza sostituire quelli funzionanti |
| Migliorare la grafica, proporre stili e mantenere il rollback | Quattro stili e copie 0.7/0.6 conservati; nessuna scelta grafica finale registrata | Mostrare le alternative con i dati del nuovo modulo e continuare la rifinitura sulla scelta dell'utente |
| Controllare tutto prima dell'uso finale | 95 test e percorso browser superati localmente | Restano installazione e collaudo sul server/rete reali; non presentare la versione come già in produzione |

**Prima azione consigliata a Codex:** leggere questo passaggio, avviare i test e il portale su un archivio dimostrativo isolato, quindi riprendere dalle statistiche e da Backup ed esportazioni. Le funzionalità recenti sono già nel codice: vanno valutate e migliorate a partire da questa base. Non iniziare nuovamente un progetto vuoto. La prossima decisione utile è individuare l'ambiente già disponibile per l'installazione e confermare la direzione grafica; le estensioni proposte restano distinte dalle richieste già attuate.

## Requisiti consolidati dell'utente

1. Il requisito iniziale EXE è stato sostituito dalla scelta esplicita **web con 2FA**. Le sedi remote lavorano con il browser su un archivio centrale.
2. Adattabilità a tutti i centri: fasce, causali, giorni lavorativi, calendari e parametri configurabili. Condizioni economiche diverse per **persona + centro + mese**.
3. Il compilatore può inserire le presenze ma non cambiare i parametri né leggere i dati HR e gli accordi riservati. La protezione deve essere effettiva sul server.
4. Registro mensile ispirato al modello Sodav: giorni orizzontali, persone e fasce su righe, contatori. Distinguere pianificato e consuntivo, assenze, riposi, esterni e festivi riconosciuti.
5. Archivio dipendenti completo, documenti, scadenze e onboarding. Questi dati erano stati sottolineati più volte dall'utente e devono essere conservati.
6. Dashboard multicentro, statistiche, esportazioni Excel per centro e complessive, più altri prospetti e backup del database.
7. Nessun acquisto o abbonamento: software e risorse gratuite per l'uso previsto; usare infrastruttura già disponibile. Hardware, rete e gestione non sono forniti dal codice.
8. UI/UX curata, ispirata a NefroCenter; più stili e rollback. L'utente non ha ancora scelto in modo definitivo uno dei nuovi stili.
9. Verificare il lavoro come sviluppatore full stack prima della consegna. Ultima richiesta: raccogliere tutto in un unico file per trasferire il lavoro a Codex.

Le richieste originali disponibili sono riportate in `CONTESTO_CONVERSAZIONE.md`. Non è una trascrizione completa di tutte le risposte precedenti dell'assistente; non va presentata come tale.

## Cosa funziona nella 0.8

| Area | Implementazione |
|---|---|
| Autenticazione | Password, attivazione nominativa, TOTP obbligatorio, recuperi monouso, anti-riutilizzo, limiti tentativi, gestione dispositivi e verifica recente delle operazioni sensibili |
| Permessi | Amministratore; responsabile dei centri assegnati; compilatore; lettore. Verifiche server su ogni lettura/scrittura; revoca sessioni ai cambi account |
| Presenze | Griglia mensile/a settimana, fasce configurabili, consuntivo/pianificato, pause, turni notturni, causali, sedi esterne, sovrapposizioni, chiusura e riapertura motivata |
| Accordi | Turni/ore/quota fissa, base totale/eccedenza, teorico calendario/manuale, tariffe e rettifiche individuali; importi solo quando confermati e calcolabili |
| HR | 53 campi standard, campi personalizzati per centro, otto sezioni, checklist configurabile con 14 attività iniziali, allegati fino a 6 MiB, scadenze, storico versioni e controlli di concorrenza |
| Statistiche | Filtri centro/periodo/ruolo/persona, ore, turni, assenze, completezza, confronti per centro/ruolo/mese, dettaglio persona, chiusure e riepilogo HR riservato |
| Excel | Sei prospetti .xlsx: centro, totali, statistiche, fascicoli, onboarding/scadenze, accordi. Filtri e autorizzazioni coerenti; date e ore tipizzate, testo non eseguito come formula |
| Backup | Copie SQLite con allegati, giornaliere mentre il servizio è acceso, manuali, integrità verificata e pubblicazione atomica; elenco e download amministratore con 2FA recente |
| Migrazione | Importazione del modello Sodav riconosciuto; migrazione dei backup desktop 0.4/0.5, con controlli e annullamento atomico |
| Interfacce | Attuale, Spazio di lavoro, Essenziale, Editoriale. Stile locale al browser, transizioni CSS e movimento ridotto, controlli mobile |

## Stato del collaudo

**95 test Python superati**, più un percorso Chromium completo contro Waitress reale. I log finali sono `qa/unit-tests.log` e `qa/browser-tests.log`. Verificati anche tutti e sei i download Excel e il download SQLite, ruoli, 2FA, ritorno con recupero, persistenza HR, risposte fuori ordine, quattro stili a 1400/1024/390/320 px e assenza di overflow esterno nei percorsi provati. Le schermate delle nuove pagine sono state ispezionate visivamente. Il problema di overflow mobile della lista backup è stato corretto prima della prova finale.

Non equivalgono a prove su server Windows, rete multisede, certificato HTTPS reale, scansione QR con telefono fisico, carico di produzione o audit indipendente. Vedere i limiti nel rapporto. I test usano solo dati dimostrativi e archivi temporanei.

## Architettura e mappa del codice

Applicazione Python con WSGI/Waitress, SQLite locale al server (WAL), frontend HTML/CSS/JavaScript nativo. Un processo applicativo. Nessun servizio esterno obbligatorio per il funzionamento quotidiano. Il browser non conserva dati HR in localStorage: vi è conservata la scelta dell'interfaccia.

| File | Responsabilità |
|---|---|
| `web_server.py` | WSGI, rotte, controllo origine/CSRF, autenticazione, download, avvio e backup giornaliero |
| `web_auth.py` | Sessioni, attivazione, TOTP, recupero, cifratura segreti, verifica recente |
| `core.py` | SQLite, autorizzazioni, CRUD, revisioni, periodi, audit e backup online |
| `rules.py`, `engine.py` | Regole delle presenze, durate, controlli e riepiloghi |
| `agreements.py` | Validazione e calcolo accordi individuali; usa Decimal per gli importi |
| `hr.py` | Profili, 53 campi, attività, documenti, scadenze e storico |
| `analytics.py` | Aggregazioni read-only in una transazione, denominatori e filtri comuni |
| `excel_exports.py` | Generazione dei sei prospetti Excel e tipizzazione delle celle |
| `backup_tools.py` | Elenco dei soli backup completati e download protetto |
| `import_excel.py` | Riconoscimento del modello Excel e delle formule note, senza eseguire VBA |
| `migrate_desktop.py`, `manage.py` | Migrazione desktop e amministrazione locale, setup, backup e after-restore |
| `ui.html`, `assets/app.js`, `assets/web_ui.js` | Struttura pagina, navigazione, API e flusso autenticazione |
| `assets/hr_ui.js`, `assets/hr_complete.css` | Fascicolo e interazioni HR |
| `assets/monthly.js`, `assets/monthly.css` | Registro mensile e accordi |
| `assets/statistics.js`, `assets/statistics.css` | Nuova sezione statistiche |
| `assets/exports.js`, `assets/exports.css` | Nuova pagina esportazioni e backup, download con verifica recente |
| `assets/themes.js`, `assets/themes.css` | Quattro stili e scelta locale |
| `test_*.py`, `qa/` | Verifiche automatiche e percorso reale del browser |
| `deploy/` | Esempi di configurazione del servizio e reverse proxy, da adattare |

Il dato delle presenze è identificato da centro, persona, giorno, fascia e livello pianificato/consuntivo. I periodi contengono la configurazione storicizzata del mese e gli accordi. Le persone sono ancora anagrafiche per centro; non esiste un'identità globale automaticamente deduplicata. Il ruolo nelle statistiche è quello attuale, non uno storico a decorrenza.

Le nuove API sono `/api/statistics`, `/api/statistics_csv`, `/api/export_xlsx`, `/api/backups` e `/api/backup_download`. Le tre prime usano `from`, `to`, `cid`, `role`, `person_id`; XLSX aggiunge `kind` e `layer`. Le operazioni richiedono sessione con secondo fattore completato. I filtri autorizzano solo i centri assegnati. Gli export privati e il backup richiedono autenticazione recente; il limite è cinque minuti.

## Avvio e test per Codex

Dalla cartella che contiene questo file:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -v
```

Per la prima prova interattiva locale, solo con archivio nuovo:

```bash
.venv/bin/python manage.py init --data-dir data --key-file private/server.key
.venv/bin/python web_server.py --data-dir data --key-file private/server.key --origin http://127.0.0.1:8080 --dev-http
```

L'inizializzazione è interattiva: crea account e chiave e mostra l'attivazione riservata. Non vi sono credenziali predefinite. Per un archivio già configurato mantenere dati e chiave e non rieseguire `init`. HTTP è ammesso soltanto sul loopback; per le sedi serve HTTPS, con configurazione del proxy/rete. La guida include anche i comandi Windows.

Il browser di collaudo usa Node.js e Playwright separati dalle dipendenze di produzione. `qa/README.md` descrive comandi e variabili; `python qa/run_browser.py` crea un archivio temporaneo e lo elimina alla fine. Gli output del test possono includere download dimostrativi e non devono essere confusi con dati operativi.

## Gratuità e risorse effettivamente usate

XlsxWriter 3.2.9 (BSD-2-Clause) produce i file Excel, incluso nel pacchetto. PyOTP 2.9.0 (MIT), Segno 1.6.6 (BSD-3-Clause), Waitress 3.0.2 (ZPL-2.1) sono inclusi. `cryptography` 50.0.2 (Apache-2.0 o BSD-3-Clause) è fissata in requirements e da installare. Roboto locale (OFL-1.1), icone Lucide Static 0.468.0 (ISC/attribuzione Feather MIT), CSS e JS nativi curano la grafica. Nessuna libreria 3D o motion pesante è stata aggiunta. Licenze e provenienza sono conservate nel pacchetto. Il logo NefroCenter è una risorsa del gruppo, non una risorsa open source.

## Punti aperti e priorità suggerite

Non sono nuove autorizzazioni a pubblicare, acquistare o inviare comunicazioni. Sono proposte di sviluppo da valutare con l'utente.

1. Collaudare installazione e rete della sede pilota: HTTPS, accessi remoti, riavvio, carico e ripristino; individuare il server già disponibile e i responsabili.
2. Aggiungere una destinazione di backup separata, conservazione configurabile e prova periodica di ripristino. Attualmente le copie automatiche sono locali; quelle esterne sono manuali.
3. Aggiungere approvazione mensile del responsabile e della direzione, con restituzione motivata.
4. Storicizzare contratti/ruoli/accordi con decorrenze infra-mese. Nessun calcolo arbitrario di straordinari, maturazioni o costo aziendale.
5. Introdurre richieste ferie/permessi e portale personale, definendo saldi e visibilità del singolo dipendente.
6. Concordare il tracciato Excel per il consulente paghe e i fabbisogni per il confronto copertura turni.
7. Separare il ruolo HR di gruppo dall'amministrazione tecnica; eventuali notifiche email richiedono configurazione e autorizzazione.

Il database HR e gli allegati non sono cifrati integralmente dall'app. Solo i segreti 2FA sono cifrati con una chiave esterna. Il backup DB da solo non contiene quella chiave: conservarla separatamente e proteggerla insieme al server. Non esiste modalità offline, sincronizzazione con Drive del database attivo, alta disponibilità o fusione automatica delle persone tra sedi.

## Fonti e materiali conservati

- `MODELLO_SODAV.md` documenta il file **Presenze personale  Sodav Febbraio  2026 sodav.xlsm**, l'impronta, 17 anagrafiche, 231 celle, i 10 confronti di formule riconosciute e le anomalie. È un riscontro delle versioni precedenti, non una nuova lettura della fonte in questa revisione. Gli accordi importati restano da confermare. L'Excel originale e il video non sono inclusi; non inventarne contenuti mancanti.
- `qa/source-check.json` conserva solo risultati aggregati e impronta della fonte; nessun nominativo reale.
- `anteprime/v0.7_conversazione.html` conserva l'anteprima storica a quattro stili con dati fittizi e 2FA simulata. È un frammento della conversazione, distinto dal servizio reale e precedente alle nuove pagine 0.8.
- `rollback/Presenze_Web_v0.7_Rollback.zip` e `rollback/Presenze_Web_v0.6_Rollback.zip` sono copie byte per byte dei pacchetti precedenti. I backup operativi dell'organizzazione non sono stati forniti e non sono inclusi. `ROLLBACK.md` spiega grafica e ripristino completo.
- `qa/history/` conserva il rapporto e gli esiti della 0.7 separati dai test finali 0.8.

## Come continuare senza perdere il lavoro

Leggere la documentazione e verificare i test prima di modificare. Creare il repository/branch di sviluppo dal contenuto estratto se non esiste già. Le dipendenze incluse e le loro licenze fanno parte della consegna. Le modifiche ai calcoli devono avere test sugli esempi e sui valori mancanti; le modifiche ai permessi vanno verificate anche chiamando direttamente le API. Per aggiornare la grafica usare il selettore degli stili e mantenere Attuale. Registrare versione, modifiche, prove eseguite e limiti effettivi. Continuare in italiano con aggiornamenti brevi, senza presentare un'anteprima come un servizio già in produzione.
