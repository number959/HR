# Statistiche, Excel e backup — versione 0.8

## Statistiche del personale

La pagina **Statistiche** usa i dati salvati nel database centrale. Filtri: centri autorizzati, intervallo di mesi (massimo 24), ruolo e persona. La persona è selezionabile dopo il centro. Filtri, grafici, dettagli e relativo Excel condividono la stessa aggregazione lato server e una lettura coerente del database.

| Indicatore | Definizione e limite |
|---|---|
| Ore registrate | Somma delle durate effettive meno le pause dei turni con orari disponibili. Un turno notturno è attribuito al giorno di inizio. Non include crediti di assenza o ore stimate. |
| Turni effettivi | Numero di fasce lavorative a consuntivo, non numero di persone o giornate. |
| Assenze registrate | Numero di fasce con causale di assenza. Due fasce nello stesso giorno contano due assenze e una sola giornata per anagrafica e centro. I riposi restano distinti. |
| Completezza orari | Turni con durata disponibile / tutti i turni lavorativi × 100. Il totale si ricalcola dai conteggi; non è la media semplice delle percentuali dei centri. |
| Quota assenze | Fasce di assenza / (fasce lavorative + fasce di assenza) × 100. Non è un tasso di assenteismo su ore contrattuali. |
| Pianificazioni senza consuntivo | Fasce lavorative pianificate senza una registrazione effettiva della stessa persona, giorno e fascia. Anche un'assenza effettiva risolve il pianificato. Include date future, quindi non rappresenta necessariamente un ritardo. |
| Chiusure e calendari | Conteggi dei mesi per ciascun centro autorizzato, con calendario verificato e chiusura. |
| Personale e onboarding | Situazione attuale dei fascicoli attivi, a prescindere dai mesi delle presenze; applica centro, ruolo e persona. Esclude persone disattivate o con rapporto terminato. Visibile solo ad amministratore e responsabili dei centri assegnati. |

Se non esistono consuntivi, le ore sono **non disponibili**. Se tutti i turni lavorativi sono senza orari, restano non disponibili. Se solo alcuni turni hanno orari, viene mostrata la somma nota con il numero di turni incompleti. Un periodo con sole assenze o riposi ha zero ore lavorate registrate, non ore stimate di assenza. Un denominatore nullo produce un indicatore non disponibile.

Le anagrafiche sono distinte per centro: la stessa persona presente in due sedi può comparire due volte. Il ruolo è quello attuale, perché non esiste ancora lo storico delle mansioni con decorrenza. Le causali con lo stesso codice ma descrizioni diverse restano separate. Registrazioni orfane di anagrafica vengono segnalate ed escluse dai conteggi; l'Excel viene bloccato finché l'archivio non viene corretto.

I grafici HTML/CSS non richiedono un servizio esterno. Il mese nel grafico, il centro nella tabella e la persona nel dettaglio permettono di approfondire i dati. Le definizioni sono disponibili nella pagina.

## Prospetti Excel realmente implementati

Aprire **Backup ed esportazioni**. Non è necessario che Excel sia installato sul server.

| Prospetto | Filtri | Fogli nel file |
|---|---|---|
| Presenze del singolo centro | Un centro, un mese; pianificato oppure consuntivo | Registro mensile con giorni in colonna e righe per persona/fascia; Totali persona; Dettaglio; Legenda; Informazioni |
| Presenze complessive | Uno o tutti i centri autorizzati; fino a 24 mesi | Totali; Centri; Andamento; Centro per mese; Ruoli; Persone; Causali; Informazioni |
| Statistiche | Stessi filtri delle statistiche; anche ruolo/persona dalla pagina Statistiche | Totali; Centri; Andamento; Centro per mese; Ruoli; Persone; Causali; Informazioni |
| Anagrafiche e fascicoli | Uno o tutti i centri autorizzati; situazione attuale | Fascicoli con 53 campi standard; Campi personalizzati; Informazioni |
| Onboarding e scadenze | Uno o tutti i centri autorizzati; situazione attuale | Attività; Scadenze; Elenco documenti (metadati, senza allegati); Informazioni |
| Accordi individuali | Uno o tutti i centri autorizzati; fino a 24 mesi | Accordi con parametri e risultati del mese; Informazioni |

Il file è un vero **.xlsx**, prodotto con XlsxWriter 3.2.9, senza macro. Date, quantità, percentuali e durate sono tipizzate: le ore usano il formato `[h]:mm` per non ripartire da zero oltre le 24 ore. Il testo degli utenti non viene interpretato come formula o collegamento automatico. Gli importi non confermati o non calcolabili rimangono vuoti. Sono copie dei risultati al momento dell'esportazione: modificare Excel non modifica il gestionale e non viene distribuito un motore di formule bidirezionale.

I file includono intestazioni, filtri, blocco dei riquadri e una scheda Informazioni. Massimo 100.000 righe complessive di dati per file; ridurre periodo/centri se superato. I consueti CSV restano disponibili nelle pagine precedenti.

Compilatore e lettore possono esportare solo dati di presenze autorizzati e solo se il permesso di esportazione è attivo in tutti i centri scelti. I prospetti HR e gli accordi sono riservati ad amministratore e responsabili dei centri assegnati; richiedono password e 2FA verificati negli ultimi cinque minuti. Le verifiche sono sul server, anche se si chiama direttamente l'API. Ogni esportazione Excel è registrata nell'audit.

## Backup del database

Sono presenti:

- Backup giornaliero verificato finché il servizio è attivo, con controllo ogni ora; copia all'avvio se manca quella del giorno.
- Comando manuale da web e console.
- Elenco delle ultime 50 copie, conteggio totale, spazio occupato e download fino a 256 MiB per file.
- Copia online coerente SQLite; controllo integrità; pubblicazione del file completato con rinomina atomica. I file parziali non sono elencati o scaricabili.
- Inclusione di dati, allegati HR, account, configurazioni e storico; verifica del ripristino nei test.
- Elenco e download solo per amministratore; download con autenticazione recente e registrazione nell'audit.

La **chiave esterna dei segreti 2FA non è dentro il database**: va conservata separatamente insieme alla configurazione del server. Il download non espone la chiave. Il ripristino va eseguito dal referente sul server, con servizio fermo e comando `manage.py after-restore`, secondo `INSTALLAZIONE_WEB.md`.

Non sono implementati cancellazione automatica/rotazione, backup remoto programmato o ripristino dal browser. Le copie automatiche sono sullo stesso server; non proteggono da sole dalla perdita dell'intero dispositivo. Il download consente di conservare una copia separata. Database e backup non sono cifrati integralmente dall'applicazione: la cifratura applicativa riguarda i segreti TOTP.

## Proposte per i prossimi sviluppi (non ancora implementate)

| Ordine | Funzione proposta | Utilità e prerequisiti |
|---|---|---|
| 1 | Copia automatica separata dei backup, politica di conservazione e prova periodica di ripristino | Protegge dalla perdita del server; scegliere una destinazione aziendale già disponibile e autorizzata. Copiare solo backup completati, mai il database attivo sincronizzato. |
| 2 | Approvazione mensile: compilatore → responsabile → direzione | Evidenzia chi deve controllare; consente restituzione motivata e chiusura solo dopo approvazione. |
| 3 | Storico contratti, mansioni e accordi con decorrenze | Gestisce cambi infra-mese e rende corretti i confronti storici; definire priorità e regole del centro/dipendente. |
| 4 | Richieste ferie/permessi e portale personale | Ogni dipendente vede i propri dati e lo stato delle richieste; i saldi richiedono maturazioni, residui e regole validate. |
| 5 | Esportazioni per il consulente paghe | Mappature dei codici concordate con chi importa i file, anteprima delle differenze e versione del tracciato. |
| 6 | Copertura turni per sede e qualifica | Confronta pianificato e fabbisogno configurato; non inventare requisiti minimi normativi. |
| 7 | Avvisi di scadenza e ruolo HR di gruppo separato dall'amministratore tecnico | Scadenzario operativo e permessi più precisi. Email solo dopo configurazione di un servizio aziendale e autorizzazione esplicita. |

Straordinari contrattuali, costo aziendale e tasso di assenteismo sulle ore previste non vengono presentati come già calcolati: mancano regole consolidate e una base storica completa di ore dovute/maturazioni. Gli accordi mensili esistenti sono una funzione distinta.
