# NefroCenter — aggiornamento 0.9

La versione 0.9 aggiunge le funzioni approvate: copie di backup su NAS, attività da completare, identità del personale di gruppo, decorrenze contrattuali ed economiche, preparazione dei dati per il consulente paghe. Include il ruolo HR centrale, la consultazione dei documenti caricati dalle sedi e guide integrate.

## Cosa cambia nell’uso quotidiano

- **Da completare:** orari mancanti, pianificazioni pregresse senza consuntivo, calendari da verificare, mesi precedenti aperti, fascicoli, onboarding e scadenze. Ogni voce apre la pagina interessata. I dati HR sono visibili solo ai ruoli autorizzati.
- **Personale di gruppo:** ogni anagrafica riceve un’identità distinta. HR può collegare esplicitamente la stessa persona tra sedi, indicando una motivazione. Nomi o matricole uguali non producono fusioni automatiche. I fascicoli e gli allegati delle sedi restano conservati. I controlli sulle sovrapposizioni fra sedi usano i collegamenti verificati: le persone non collegate non sono riconosciute automaticamente come la stessa persona.
- **Decorrenze:** ruolo, contratto, CCNL, livello, ore settimanali e part-time hanno date di validità e storico. Le condizioni economiche si applicano al mese con anteprima e conferma. Un cambio infra-mese di tariffa a turni/ore può essere calcolato sui rispettivi giorni; quote fisse, teorici e conguagli richiedono un accordo mensile manuale verificato. Gli accordi già applicati al mese conservano una copia dei parametri; modificare le decorrenze non li riscrive automaticamente.
- **Paghe:** modello configurabile per centro, colonne e intestazioni, causali e matricole, anteprima anomalie e CSV/XLSX. Il modello iniziale è una bozza generica: non è certificato per un gestionale del consulente. Prima del download definitivo occorrono mappature verificate, conferma del modello e assenza di anomalie bloccanti. Il sistema esporta dati di presenza, non calcola buste paga, imposte o contributi.
- **Documenti HR:** elenco centrale filtrabile e visualizzazione protetta di PDF, PNG e JPEG; il caricamento dalle sedi sullo stesso server è immediatamente disponibile all’ufficio HR. Visualizzazioni e download sono registrati.
- **NAS:** seconda copia di backup completati, verifica delle impronte, integrità SQLite e allegati, conservazione configurabile e prova tecnica di lettura su copia temporanea. Configurazione inizialmente disattivata; serve il percorso reale montato sul server. Il database attivo resta sul disco locale. La chiave 2FA va custodita e copiata separatamente.
- **Guide e tutorial:** guida per pagina, riferimento delle impostazioni, percorsi guidati sui comandi visibili e 28 videoguide illustrate senza audio, con sottotitoli e trascrizioni. Disponibili anche in `GUIDE_UTENTE.md`.

## I punti 2 e 7 spiegati

**2 — Approvazione del mese.** È un flusso aggiuntivo proposto: la sede completa e invia il mese, il responsabile lo approva oppure lo restituisce con una nota, HR procede alla chiusura. Serve quando si vuole distinguere “ho compilato” da “qualcuno ha controllato”. Non è stato attivato: rimangono verifica calendario, chiusura e riapertura motivata già presenti. Richiede una scelta su chi invia, chi approva e se la stessa persona può ricoprire entrambi i ruoli.

**7 — Interfacce e profili.** Ogni persona vede le funzioni consentite al suo ruolo. Il nuovo profilo **HR centrale**, necessario per la richiesta sui documenti, consulta tutti i centri e gestisce fascicoli, documenti e funzioni del personale. Non gestisce account, backup tecnici, presenze o parametri del centro. I responsabili restano limitati ai centri assegnati; i compilatori non vedono i fascicoli riservati. Un eventuale ulteriore ridisegno completo dei percorsi per ruolo resta una scelta separata.

## Aggiornare un’installazione esistente

1. Fermare il servizio e conservare una copia completa della cartella dati, della chiave originale e del codice attuale. Non sovrascrivere dati o chiave con contenuti del pacchetto.
2. Estrarre il nuovo codice in una cartella separata e usare i percorsi di dati e chiave già configurati. Installare le dipendenze in un ambiente Python dedicato.
3. All’avvio, prima delle modifiche allo schema precedente, viene creata una copia preventiva. Le nuove tabelle sono aggiunte e ciascuna anagrafica esistente riceve un’identità distinta. Le presenze e gli allegati esistenti vengono mantenuti.
4. Provare accessi 2FA, centro pilota, consultazione HR, allegati, export e backup. Per il NAS impostare il percorso reale e verificare “Copia e prova ripristino”.
5. Per tornare al codice precedente usare anche il database e la chiave corrispondenti alla copia precedente all’aggiornamento. Conservare a parte i dati successivi: il ripristino a una copia precedente non li include. Vedere `ROLLBACK.md`.

La prova tecnica dei backup non verifica il montaggio reale del NAS, i permessi aziendali, la disponibilità del server o l’intero processo di ripristino e accesso. Questi controlli vanno completati dal tecnico sul sistema definitivo.

## Installazione e demo

`INSTALLAZIONE_IN_BREVE.md` spiega dove installare il gestionale e cosa serve. `INSTALLAZIONE_WEB.md` contiene i comandi. La demo condivisibile è separata dall’installazione: usa esclusivamente dati fittizi e copie di lavoro indipendenti per visitatore; non è l’archivio operativo HR.

**Demo online:** https://nefrocenter-demo.icy-bass-2671.chatgpt.site. Puoi condividere il link senza creare account. Scegli un profilo per iniziare; non inserire dati reali.

Il collaudo finale include 150 test Python superati e i percorsi Chromium completi di gestionale e demo. Dettagli e limiti in `VERIFICA.md`.
