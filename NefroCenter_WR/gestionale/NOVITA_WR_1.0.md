# NefroCenter WR · Work Resources 1.0 — cosa cambia rispetto alla 0.11

NefroCenter WR è la riscrittura completa di «Persone e Presenze Web 0.11»: stesse funzioni, nuovo motore, nuova interfaccia, nuovo nome. I dati della 0.11 si portano in WR con la migrazione (`MIGRAZIONE_DALLA_0.11.md`); la 0.11 resta intatta.

## Il motore

- Un solo pacchetto Python (`wr/`) con moduli piccoli e separati: presenze, mesi, approvazioni, accordi, persone e fascicoli, documenti e verifiche, personale di gruppo, copertura e sostituzioni, uscite e dotazioni, paghe, statistiche, esportazioni, comunicazioni, promemoria, backup, importazione Excel, migrazione.
- Archivio SQLite nuovo (schema WR 1) con vincoli espliciti e versioni ottimistiche su tutto: due persone che salvano lo stesso dato non si sovrascrivono a vicenda.
- Parametri della struttura **versionati**: ogni mese ricorda con quali parametri è stato compilato; i cambi valgono dai mesi non ancora compilati.
- Regole di dominio in un unico posto (`rules.py`): fasce, causali, festività nazionali calcolate, riposo minimo, sovrapposizioni anche fra strutture diverse della stessa persona.
- Sicurezza: password (PBKDF2), app Authenticator (TOTP) con segreti cifrati dalla chiave del server, codici di recupero monouso, conferma di sicurezza per le operazioni sensibili (5 minuti), sessioni che scadono dopo 15 minuti di inattività, intestazioni di sicurezza e Content Security Policy severa, token anti-falsificazione, limiti di tentativi.
- Demo pubblica con **lo stesso motore**: il codice Python gira nel browser (Pyodide), così la demo mostra esattamente le regole del portale senza un server. Nessun dato lascia la scheda del browser.
- Nessuna dipendenza da installare oltre a `cryptography` e `tzdata`: Waitress, XlsxWriter e Segno sono inclusi.

## L'interfaccia

- Menu per aree (Panoramica, Presenze, Persone, Amministrazione, Analisi, Sistema, Aiuto) che mostra solo ciò che il profilo può fare; barra superiore con struttura e mese sempre a portata di mano.
- Riepilogo con numeri del mese e **Da completare**: elenco automatico di orari mancanti, pianificati da consuntivare, fascicoli e documenti, scadenze, approvazioni, sostituzioni, backup, importazioni da verificare. Le voci spariscono da sole quando il dato è sistemato.
- Registro presenze con vista **Mese** e vista **Giorno** (pensata per il telefono), livelli Consuntivo e Pianificato, ricerca e filtro per ruolo, avvisi leggibili (turni senza orari, riposo insufficiente, importazioni da verificare).
- Guida contestuale «?» in ogni pagina, Guida completa con procedure, pagine, domande frequenti, manuale e videoguide; pagina **Ruoli e permessi** con la stessa tabella usata dal server.
- Tema chiaro e scuro, tastiera e lettori di schermo, nessun testo tagliato anche su telefono (390 px).
- Grafici delle statistiche semplici e leggibili (una serie, un asse, valore al passaggio del mouse o con la tastiera).

## Le funzioni

Tutte le funzioni della 0.11 sono presenti: registro e pianificazione, controlli e chiusura del mese, approvazione mensile (invio, approvazione o restituzione con motivazione, blocco dopo l'invio), accordi e calcoli (turni, ore, fisso; festivi CCNL), persone e fascicoli con inserimento guidato, documenti con verifica HR, personale di gruppo e identità, copertura turni e sostituzioni fra strutture, uscite e dotazioni, rubrica strutture, comunicazioni (modelli, liste, bozze, anteprime, invio a lotti), promemoria, paghe con tracciato del consulente, statistiche ed esportazioni CSV/Excel, backup locale e seconda copia verificata, importazione del modello Excel.

Migliorie rispetto alla 0.11:

- **Importazione Excel sul modello reale**: il file compilato dagli uffici (anche con celle fuori standard) non blocca più l'importazione: le celle non riconosciute vengono elencate e restano da completare a mano; vengono letti festività, festivi CCNL nelle formule, pazienti per fascia, pazienti di riferimento, sezioni dipendenti/collaboratori, foglio «Collaboratori» (come promemoria, mai l'IBAN); il mese può essere aggiunto a una struttura esistente con lo stesso nome.
- Persone ripetute nel modello (stessa persona con due ruoli) diventano una sola scheda.
- Festività nazionali calcolate per ogni anno (Pasquetta compresa); il patrono si aggiunge nei parametri.
- Segnalazioni «da verificare» su ogni registrazione importata con dati incerti, visibili nel registro e in Da completare.
- Backup verificati con prova di ripristino programmata; nessuna destinazione preimpostata.

## Cosa resta da fare in azienda

- Installare il portale sul server aziendale (`INSTALLAZIONE.md`) e provarlo sulla rete reale con una struttura pilota.
- Configurare la seconda copia dei backup sul NAS, il servizio di posta e il tracciato del consulente paghe: tutto arriva spento e senza parametri presunti.
- Decidere se la demo pubblica WR sostituisce o affianca quella della 0.11 (`../demo/LEGGIMI.md`).
