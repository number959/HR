# NefroCenter — Persone e Presenze

## Documento per la presentazione all’ufficio HR

**Versione 0.11 · edizione qualità 0.11.1 · 23 ottobre 2026**

**NefroCenter è un portale condiviso per gestire persone, presenze, documenti e comunicazioni tra le strutture e l’ufficio HR centrale.** Il programma operativo si installa su un server aziendale; gli utenti delle sedi lo aprono dal browser e lavorano sullo stesso archivio, con accessi diversi secondo il ruolo.

La demo è disponibile su **https://nefrocenter-demo.icy-bass-2671.chatgpt.site**. Si può condividere il collegamento senza creare account: usa dati inventati e ogni visitatore prova una copia separata. Il gestionale operativo deve ancora essere installato e configurato nell’ambiente aziendale.

Questo documento spiega le funzioni attuali, il loro utilizzo quotidiano e le decisioni necessarie per l’avvio. Il manuale `GUIDE_UTENTE.md` e l’aiuto nel portale descrivono invece procedure e singole impostazioni.

## 1. Il messaggio da presentare a HR

> «Il software raccoglie in un unico portale le informazioni che oggi possono essere distribuite fra registri presenze, file Excel, documenti delle sedi e comunicazioni email.
>
> Ogni struttura può compilare le presenze e aggiornare i fascicoli per cui è autorizzata. HR centrale può consultare i documenti caricati dalle sedi, seguire ingressi e scadenze, mantenere i riferimenti delle strutture e preparare comunicazioni a gruppi di destinatari.
>
> La dashboard e la pagina “Da completare” aiutano a individuare orari mancanti, attività aperte e scadenze. Le statistiche confrontano i dati dei centri; gli export preparano prospetti e dati da concordare con il consulente paghe.
>
> Gli accessi distinguono amministrazione tecnica, HR centrale, responsabili, compilatori e lettori. Il compilatore delle presenze non accede ai fascicoli riservati. Nel sistema operativo gli account sono nominativi e richiedono un secondo fattore.
>
> Abbiamo una demo condivisibile, guide per le pagine e una presentazione video. Per l’avvio effettivo occorre scegliere una sede pilota, assegnare i ruoli, verificare i parametri, configurare il server e il NAS e concordare il servizio email e il tracciato del consulente. Il programma prepara e organizza il lavoro; il calcolo delle buste paga e gli adempimenti obbligatori restano nei sistemi e nelle procedure competenti.»

## 2. Un esempio concreto: dalla sede a HR centrale

Una nuova persona entra in una struttura. Il responsabile autorizzato apre il suo fascicolo, inserisce dati anagrafici e contrattuali, avvia la checklist di ingresso e carica il contratto in PDF. Può indicare categoria e scadenza del documento.

Il file viene salvato sul server centrale. **HR centrale lo trova nel fascicolo e nell’archivio “Documenti HR”, anche se il caricamento è stato effettuato da una sede remota.** Non occorre trasferire una seconda copia via email. Nell’installazione operativa, sede e HR devono collegarsi allo stesso server.

HR controlla i dati, segue le attività ancora aperte e, quando la posta aziendale è stata configurata, può preparare un messaggio di benvenuto o una richiesta di completamento. Durante il mese il compilatore registra le presenze; il responsabile verifica anomalie e calendario e chiude il mese. Gli utenti autorizzati consultano statistiche, accordi e prospetti per il consulente.

Il caricamento dei documenti è riservato ai ruoli HR autorizzati. **Non è presente un portale personale separato in cui ogni dipendente entra automaticamente per caricare i propri file.**

## 3. Le funzioni, pagina per pagina

### Dashboard: vedere la situazione dei centri

Raccoglie i centri autorizzati e i principali totali del mese: turni, ore disponibili, stato dei mesi e dati da completare. Permette di passare dalla visione d’insieme alla struttura interessata e di esportare un riepilogo CSV. Si aggiorna periodicamente e dispone di un comando di aggiornamento manuale.

Per HR serve a capire dove concentrare i controlli. La visione complessiva dipende sempre dai centri e dalle informazioni consentiti al profilo.

### Da completare: organizzare il lavoro aperto

Presenta attività ricavate dai dati: orari assenti, pianificazioni passate senza consuntivo, calendari non verificati, mesi precedenti ancora aperti, fascicoli da compilare, checklist incomplete e scadenze. Ogni voce porta alla pagina pertinente.

Le informazioni HR sono riservate ai ruoli abilitati. L’amministratore vede anche eventuali problemi della seconda copia dei backup. È una lista operativa aggiornata dai dati. La pagina Promemoria permette inoltre di configurare riepiloghi automatici delle scadenze ai referenti autorizzati.

### Presenze: pianificazione e lavoro effettivo

Il registro mensile dispone le persone sulle righe e i giorni sulle colonne, con fasce configurabili, per esempio mattina, pomeriggio e sera. È disponibile anche una vista di sette giorni, utile sugli schermi piccoli.

Il **pianificato** descrive il turno previsto; il **consuntivo** descrive quanto registrato come svolto. Si possono gestire causali di lavoro, assenza e riposo, ingresso e uscita, pause, turni che superano la mezzanotte, sede di lavoro, festivi riconosciuti e note. Il ruolo del compilatore può essere limitato su orari, pianificazione, eliminazione, cambio sede e classificazione dei festivi.

Il registro distingue ore effettivamente determinabili, turni senza orario, credito delle assenze, lavoro fuori sede e pianificazioni ancora da consuntivare. Un dato mancante rimane segnalato: non viene trasformato arbitrariamente in zero o in un turno di durata presunta. I controlli evidenziano incompatibilità e sovrapposizioni pertinenti.

È un registro compilato nel portale: il campo “badge” nel fascicolo non implica un collegamento già attivo a un terminale di timbratura.

### Dipendenti: il fascicolo della persona

Il fascicolo comprende anagrafica, recapiti, contratto, amministrazione, qualifiche, onboarding, documenti, scadenze e riferimenti della struttura. I dati includono, secondo necessità, matricola, dati personali e contatti, email aziendale, estremi del rapporto, CCNL e livello, ore settimanali e part-time, sede e reparto, responsabili, informazioni di pagamento e qualifiche.

Sono previsti **53 campi standard**, campi personalizzati configurabili per centro e cronologia delle modifiche. La persona può essere in ingresso, in servizio o cessata; l’abilitazione alla compilazione delle presenze è distinta dalla conservazione dei dati storici. Dal fascicolo si possono aprire le presenze della persona e i riferimenti al suo accordo mensile.

### Onboarding: seguire l’ingresso della persona

La checklist organizza gli adempimenti interni prima e dopo l’ingresso. Le attività hanno descrizione, responsabile, scadenza e stato: da fare, in corso, completata o non applicabile. Per la non applicabilità è richiesta una motivazione.

Il modello del centro è personalizzabile; le scadenze iniziali possono essere calcolate rispetto alla data d’ingresso. HR vede l’avanzamento e le attività scadute. La checklist non invia comunicazioni obbligatorie come UNILAV e non certifica l’esecuzione degli adempimenti esterni.

### Documenti e scadenze: archivio condiviso e controlli

Si possono allegare **PDF, PNG e JPEG fino a 6 MiB per documento**, classificandoli e indicando una scadenza facoltativa. Gli utenti autorizzati possono consultarli e scaricarli; visualizzazioni e download sono registrati. La rimozione richiede una motivazione; copie precedenti possono rimanere nei backup.

La pagina **Documenti HR** offre una ricerca centrale per struttura, persona, categoria e scadenza. HR centrale e amministratori operano su tutti i centri; i responsabili restano nel proprio perimetro.

Le scadenze derivano dai dati salvati: contratto, documenti, qualifiche e onboarding. Il portale le raccoglie per il controllo operativo. I promemoria email automatici sono disponibili, ma restano disattivati fino alla configurazione e conferma dei destinatari da parte dell’amministratore.

HR centrale e amministratori possono marcare un documento **Verificato** oppure **Da correggere**, con motivazione. La sede può richiedere una nuova verifica dopo la correzione. Lo storico conserva i passaggi e le versioni; una scadenza trascorsa resta evidenziata anche per un documento verificato in passato. Gli allegati preesistenti non vengono considerati verificati automaticamente.

### Personale di gruppo: riconoscere la persona tra più sedi

Consente di collegare esplicitamente le anagrafiche della stessa persona presenti in strutture diverse, con motivazione e storico. Nome o matricola uguali non determinano fusioni automatiche. I fascicoli delle sedi e i loro allegati rimangono conservati.

I collegamenti verificati permettono anche controlli sulle sovrapposizioni tra sedi. Senza un collegamento non si presume automaticamente che due anagrafiche rappresentino la stessa persona.

Il modulo conserva inoltre **decorrenze contrattuali ed economiche**: ruolo, contratto, CCNL, livello, ore settimanali e part-time possono avere intervalli di validità. Le condizioni economiche si applicano al mese tramite anteprima e conferma. Cambi di tariffa a turni o ore durante il mese possono usare i rispettivi periodi; quote fisse, teorici e conguagli richiedono nei casi previsti un accordo mensile manuale verificato. Le modifiche allo storico non riscrivono automaticamente gli accordi già applicati.

### Strutture: rubrica collegata ai fascicoli

Ogni struttura dispone di 16 riferimenti: ragione sociale, partita IVA, codice fiscale, indirizzo, comune, CAP, provincia, telefono, email generale, email HR, email amministrativa, PEC, referente, direttore, sito web e note organizzative.

I recapiti della struttura sono visibili dal fascicolo del dipendente. **Aggiornare la rubrica aggiorna il riferimento condiviso**, evitando di ricopiare lo stesso contatto in ogni scheda. Questa operazione non trasferisce il dipendente ad altra sede e non cambia i parametri del registro. La PEC è un recapito conservato in rubrica; non attiva un servizio di invio PEC certificato.

### Accordi e calcoli: condizioni individuali del mese

Gli accordi sono distinti per persona, struttura e mese. Si possono usare modelli a turni, a ore o a quota fissa, selezionare il conteggiabile, confrontarlo con un teorico e impostare tariffe feriali e festive, detrazioni, integrazioni e rettifiche motivate.

Le condizioni importate o proposte devono essere verificate e confermate. Il modello a ore richiede orari sufficienti; se mancano, il risultato può rimanere non calcolabile. Compilatori e lettori non accedono agli accordi economici riservati.

Questi risultati servono alla gestione degli accordi previsti: **non calcolano contributi, imposte o netto in busta** e non costituiscono un motore generale di applicazione dei contratti collettivi o degli straordinari.

### Riepilogo e Controlli: arrivare alla chiusura

Il riepilogo presenta turni, giorni, ore disponibili, fuori sede, festivi, assenze e dati da consuntivare. Sono disponibili stampa e file CSV secondo i permessi. La pagina Controlli raccoglie anomalie, verifica del calendario e storico applicativo.

Senza il flusso aggiuntivo, amministratori e responsabili autorizzati chiudono il mese e lo riaprono con motivazione. La chiusura impedisce le normali modifiche al periodo.

### Approvazione mese: sede, responsabile, HR

L’amministratore può attivare il percorso per ciascuna struttura. La sede invia il mese; da quel momento il registro è bloccato. Il responsabile verifica calendario e registrazioni e passa il mese a HR. HR centrale o l’amministratore approva e chiude il periodo dopo i controlli bloccanti. Una restituzione motivata riapre la compilazione. Una modifica dei dati di riferimento dopo l’invio richiede una nuova verifica.

La pagina mostra stato, controlli, passaggio disponibile e storico con autore, data e motivazione. I mesi già chiusi restano riconoscibili come storico precedente: non viene attribuita loro un’approvazione HR retroattiva. L’esportazione paghe controlla l’approvazione quando il percorso è attivo.

### Copertura turni: fabbisogni e sostituzioni

Il responsabile configura minimi per giorno della settimana, fascia e qualifica, con eccezioni per data. La pagina confronta fabbisogno, pianificato e consuntivo e segnala scoperture e turni esclusi per indisponibilità o conflitti.

HR e responsabili registrano disponibilità, indisponibilità e preferenze. Le note sono riservate; compilatori e lettori vedono i conteggi aggregati. Si può proporre un turno sostitutivo fra anagrafiche già collegate alla stessa identità di gruppo. Il responsabile della sede di destinazione accetta o rifiuta: l’accettazione crea il pianificato solo se permessi, disponibilità, periodo e conflitti risultano ancora validi. I minimi sono riferimenti organizzativi da concordare; non certificano l’adeguatezza clinica.

### Statistiche: confrontare dati e completezza

Consente analisi per centro, periodo fino a 24 mesi, ruolo e persona: ore, turni, assenze per causale, presenza fuori sede, festivi, pianificazioni senza consuntivo e completezza degli orari. Comprende andamenti e confronti tra sedi; il riepilogo HR riservato riguarda fascicoli, onboarding e scadenze.

Le statistiche dichiarano i dati mancanti. Per esempio, la quota di assenze basata sulle fasce registrate non va presentata come un tasso di assenteismo sulle ore contrattuali. I ruoli possono seguire le decorrenze registrate; in mancanza di storico non viene ricostruita una qualifica passata presunta.

### Paghe: preparare il passaggio al consulente

Il modulo prepara esportazioni CSV e XLSX attraverso un modello configurabile per centro: colonne, intestazioni, separatori, causali e matricole. Si può importare la sola intestazione CSV del consulente o una specifica JSON, mappare le colonne e indicare fornitore, versione, formato data e codifica. L’anteprima segnala anomalie e richiede verifiche prima del download definitivo. Il modello deve essere confermato esplicitamente dopo il confronto con le specifiche del consulente; non è un collegamento diretto a un suo account.

Il gestionale usato dal consulente non è ancora noto: il modello iniziale è una **bozza generica da concordare**. Non esiste una compatibilità certificata già dichiarata con uno specifico fornitore. Il portale esporta dati utili al consulente; non produce cedolini.

### Comunicazioni: modelli e liste email

HR centrale e amministratori possono creare modelli e liste, personalizzare un testo, verificarlo e conservarlo come bozza. Sono inclusi cinque modelli iniziali modificabili: **benvenuto, documenti da completare, promemoria scadenze, verifica presenze e comunicazione alla struttura**.

Le liste selezionano dipendenti o contatti delle strutture. Possono filtrare le sedi e, per i dipendenti, ruolo e stato del rapporto. L’utente sceglie espressamente email aziendale o personale; per le strutture può scegliere il recapito generale, HR o amministrativo. Sono previste esclusioni di indirizzi.

L’anteprima ricalcola i destinatari, elimina duplicati, segnala indirizzi mancanti o non validi e mostra il messaggio personalizzato. La bozza conserva destinatari e testi verificati: una successiva modifica alla rubrica non riscrive la comunicazione già preparata.

L’invio reale richiede un servizio SMTP aziendale configurato e una conferma esplicita. Ogni email ha **un solo destinatario**; la lista non compare in copia agli altri. Gli invii procedono per lotti di massimo 20, con un limite orario configurabile. Il successivo lotto richiede una nuova azione.

Lo storico distingue messaggi accettati dal server, falliti e incerti. “Accettato” non significa ricevuto o letto. Gli esiti incerti non vengono ritentati automaticamente; il comando di riconciliazione di un invio interrotto non spedisce nuovi messaggi.

**Il fornitore di posta non è ancora stato scelto e SMTP nasce disattivato.** La demo simula soltanto gli invii. Non sono inclusi allegati alle campagne, campagne newsletter ricorrenti o l’integrazione OAuth/API specifica dei fornitori. I promemoria delle scadenze seguono la configurazione separata descritta sotto.

### Promemoria: riepiloghi automatici delle scadenze

L’amministratore sceglie strutture, argomenti, giorni di anticipo, orario italiano, limite giornaliero e indirizzi HR delle strutture e/o ufficio centrale. L’anteprima mostra i destinatari e i riepiloghi prima della conferma. HR centrale può consultare configurazione, anteprima e storico.

I messaggi contengono conteggi e un invito ad aprire il portale, senza nomi di dipendenti né allegati riservati. Il servizio deve restare acceso. Il programma evita il reinvio dello stesso evento e sospende i casi dall’esito incerto; dopo un ripristino i promemoria tornano disattivati. Nella demo non parte alcuna email.

### Uscite e dotazioni: chiudere le attività amministrative

HR e responsabili aprono percorsi di cessazione o trasferimento con data, referente e motivazione. Il trasferimento indica la destinazione autorizzata. La checklist segue badge, chiavi, dispositivi, documenti e accessi; ogni attività ha stato, scadenza, responsabile e nota.

Si registrano consegna e restituzione di badge, chiavi e dispositivi, con codice inventario, data e condizione. Il completamento del percorso richiede le attività obbligatorie concluse o motivate come non applicabili e tutte le dotazioni restituite. L’annullamento non simula una restituzione. Lo storico conserva i passaggi.

Il percorso organizza e documenta il lavoro: non disattiva da solo account esterni e non trasferisce o cessa automaticamente l’anagrafica. I referenti completano queste operazioni nei rispettivi sistemi dopo le verifiche.

### Parametri, Centri e Carico: adattare la sede

Amministratori e responsabili configurano, nel proprio ambito, fasce, causali, ruoli, calendario, regole e permessi del compilatore. Le configurazioni sono versionate. La creazione dei centri e l’importazione del modello Excel previsto sono riservate all’amministratore; l’importazione propone dati da verificare e non interpreta qualsiasi foglio Excel arbitrario.

La pagina **Carico** registra conteggi aggregati di pazienti ordinari e in contumacia per giorno e fascia e li confronta con il personale e i riferimenti configurati. Non gestisce anagrafiche cliniche dei pazienti. Gli indici sono un supporto organizzativo, non una certificazione dell’adeguatezza clinica o normativa della dotazione.

### Backup ed esportazioni: consegnare prospetti e proteggere l’archivio

Sono disponibili sei tipi di Excel: registro del centro, presenze complessive, statistiche, fascicoli, onboarding/scadenze e accordi, sempre secondo i permessi. I file HR ed economici restano riservati.

L’amministratore gestisce backup del database, comprensivi degli allegati, e la seconda copia su **NAS**, con controlli di integrità, conservazione e prova tecnica di lettura. La copia NAS va attivata dopo aver configurato un percorso aziendale raggiungibile. Il database attivo rimane sul disco locale del server; la chiave di sicurezza va custodita separatamente. Il ripristino richiede una procedura tecnica e la verifica degli accessi e degli invii email già effettuati.

### Sicurezza, utenti e aiuto

Gli account operativi sono nominativi, con password e codice Authenticator. Ogni utente può gestire la propria sicurezza, i codici di recupero e le sessioni; le operazioni sensibili possono richiedere una nuova verifica. L’amministratore assegna ruoli e centri e gestisce i ripristini degli account.

Il portale comprende **34 argomenti guidati, 323 riferimenti alle impostazioni e 34 videoguide illustrate senza audio**, con sottotitoli e trascrizioni. “Aiuto per questa pagina” apre la guida pertinente; i tutorial indicano i comandi visibili. Sono disponibili quattro stili di interfaccia, senza cambiare dati o permessi.

La **presentazione del prodotto** è un video separato di 2 minuti e 37 secondi in Full HD a 30 fps, disponibile con voce sintetica italiana e senza audio. Si apre anche dalla schermata iniziale della demo.

## 4. Chi deve usare ciascun ruolo

| Ruolo | Scopo e perimetro | Operazioni principali | Limiti principali |
|---|---|---|---|
| **Amministratore** | Gestione del sistema e di tutti i centri | Tutte le funzioni operative; creazione centri, account e permessi; configurazione SMTP, importazioni e backup/NAS | È un profilo esteso: va assegnato a chi deve realmente amministrare il sistema |
| **HR centrale** | Coordinamento del personale di tutte le sedi | Fascicoli, documenti centrali, onboarding, scadenze, rubrica strutture, identità di gruppo, decorrenze, preparazione paghe, comunicazioni, verifica documenti, approvazione finale del mese, disponibilità, uscite e dotazioni; consulta presenze, risultati e promemoria | Non modifica direttamente il registro presenze o i parametri del centro; può approvare la chiusura nel percorso mensile. Non gestisce account, SMTP e backup tecnici |
| **Responsabile centro** | Gestione delle sedi assegnate | Presenze, parametri, verifica mensile, fabbisogni e sostituzioni; fascicoli e documenti, richieste di nuova verifica; uscite e dotazioni, rubrica, carico, accordi, decorrenze e paghe nel proprio ambito | Non accede a sedi non assegnate né effettua la verifica documentale o l’approvazione finale riservate a HR; niente Comunicazioni email, creazione centri, amministrazione account o backup tecnici |
| **Compilatore** | Compilazione del registro dei centri assegnati | Inserisce o aggiorna presenze nei mesi aperti e non inviati; può inviare il mese al responsabile; consulta copertura aggregata, riepiloghi e controlli; altre azioni dipendono dai permessi del centro | Non accede a fascicoli, documenti HR, accordi economici, paghe o comunicazioni; non cambia i parametri né chiude il mese |
| **Direzione / lettore** | Consultazione dei centri assegnati | Dashboard, presenze, riepiloghi, controlli e statistiche; esportazioni quando autorizzate | Non modifica dati e non accede a fascicoli HR, documenti riservati o accordi economici |

Un lettore può avere tutti i centri assegnati, ma non li riceve automaticamente come HR centrale. Nella demo il lettore mostra una visione di gruppo di esempio.

HR centrale può gestire e applicare le decorrenze economiche tramite il percorso con anteprima di “Personale di gruppo”; la modifica diretta dell’accordo mensile manuale resta ai responsabili e amministratori. La consultazione di una pagina non implica il diritto di modificarne tutte le funzioni. Non esiste un ruolo autonomo “dipendente” con accesso personale automatico.

## 5. Come mostrare la demo in dieci minuti

1. **Minuti 0–2:** mostrare la presentazione con audio e spiegare che i dati sono fittizi.
2. **Minuti 2–3:** entrare come **Responsabile centro**, aprire Dipendenti e un fascicolo; mostrare struttura di riferimento, onboarding e documenti. Usare esclusivamente un allegato dimostrativo.
3. **Minuti 3–5:** scegliere **Cambia profilo → HR centrale**; aprire Documenti HR e cercare il documento della sede. Mostrare poi scadenze e attività da completare.
4. **Minuti 5–7:** in Comunicazioni scegliere modello e lista, generare l’anteprima, mostrare il testo per destinatario e usare **Simula invio**. Nessuna email viene spedita.
5. **Minuti 7–9:** passare a **Compilatore** per mostrare il registro e i limiti del ruolo; poi a **Direzione / lettore** per la consultazione e le statistiche.
6. **Minuto 9–10:** mostrare Guide e tutorial e descrivere il percorso di avvio aziendale.

I cambi di profilo nella stessa scheda mantengono la copia di lavoro dimostrativa. Un altro visitatore non vede le modifiche di questa sessione. “Ripristina demo” permette di tornare ai dati iniziali. Gli Excel dimostrativi rappresentano i dati iniziali; il CSV del registro riflette le modifiche della sessione.

## 6. Cosa serve per utilizzarlo davvero

Occorrono un server centrale disponibile, Python e le dipendenze indicate nel pacchetto, collegamento HTTPS dalle sedi, account nominativi, secondo fattore e una procedura di gestione. Alle postazioni basta il browser; per lavorare serve la connessione al server.

Prima dell’avvio HR e IT devono concordare:

- elenco delle strutture, persone autorizzate e responsabilità di compilazione e controllo;
- dati obbligatori, categorie dei documenti, checklist di ingresso e criteri di conservazione;
- fasce, causali, calendari, accordi e regole da verificare nella sede pilota;
- tracciato accettato dal consulente paghe e relative mappature;
- servizio email, mittente autorizzato, destinatari e responsabilità degli invii;
- percorso NAS, protezione delle chiavi, tempi di backup e prova di ripristino.

Il primo avvio va collaudato con una sede pilota: accessi, presenze di un mese, fascicolo, documento caricato da remoto e consultato da HR, esportazione e ripristino di prova. Il sistema comprende controlli applicativi e di accesso, ma la protezione del server e dei backup e l’organizzazione del trattamento dei dati restano attività aziendali. Non viene dichiarata una certificazione automatica di conformità.

## 7. Materiali da utilizzare nella riunione

- **Demo:** https://nefrocenter-demo.icy-bass-2671.chatgpt.site
- **Video con voce italiana:** `Presentazione_NefroCenter_v0.10_con_audio.mp4` — pulsante “Guarda la presentazione” nella demo.
- **Video senza audio:** `Presentazione_NefroCenter_v0.10.mp4`.
- **Questo documento:** `PRESENTAZIONE_PER_UFFICIO_HR.pdf`, con copia modificabile in `PRESENTAZIONE_PER_UFFICIO_HR.md`.
- **Installazione in breve:** `INSTALLAZIONE_IN_BREVE.md`.
- **Manuale completo:** `GUIDE_UTENTE.md` e aiuto integrato.
- **Servizio di posta:** `docs/SMTP_CONFIGURAZIONE.md` nel pacchetto del gestionale.

I risultati aggiornati dei test Python e dei collaudi del gestionale e della demo sono riportati in VERIFICA.md. La presentazione video comprende anche approvazioni, verifica documentale, copertura, promemoria, paghe e uscite della versione 0.11. Per i passaggi operativi usa le guide illustrate delle singole pagine. Queste prove non sostituiscono il collaudo sul server aziendale, sul NAS e sul servizio SMTP effettivamente scelto.
