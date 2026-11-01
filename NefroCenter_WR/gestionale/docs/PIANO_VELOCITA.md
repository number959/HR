# Piano «ultra veloce» — NefroCenter WR

Obiettivo: ogni azione quotidiana deve sembrare **istantanea** anche con 3000 dipendenti, 60 strutture e 150 utenti collegati dalle sedi. Il piano non cambia database né linguaggio. Le misure del 30 ottobre 2026 mostrano che il tempo si perde in quattro punti precisi, tutti nel nostro codice, e che ognuno ha una cura provata o misurata.

Da dove viene il piano: misure nel browser (Playwright) e sul servizio web reale con l'archivio fittizio da 3000 dipendenti (`docs/DIMENSIONAMENTO_ARCHIVIO.md`), due prototipi misurati (statistiche dal database, riepilogo persona × mese) e due audit indipendenti del codice, uno del server e uno del browser. In ogni audit un secondo revisore ha ricontrollato ogni rilievo sul codice. Del secondo audit sono stati confermati 18 rilievi su 20. I due scartati sono il mirino della griglia, con effetto trascurabile, e la compressione nel servizio, perché Caddy comprime già e quindi resta facoltativa. I revisori hanno aggiunto alcuni problemi non visti al primo giro, fra cui il manuale da 11,6 MB. Tutti i numeri sono misurati, salvo dove è scritto «stima». «Rete locale» indica il browser sullo stesso server. «Sede» indica una rete simulata come una VPN: 40 ms di andata e ritorno, 20 Mbit/s, un PC lento la metà del server, senza compressione. In esercizio Caddy comprime e quel caso migliora di circa 0,3 s per ogni scaricamento del registro.

## 1. Cosa vuol dire «ultra veloce»: gli obiettivi

| Azione | Oggi, rete locale | Oggi, sede | Obiettivo | Su cosa si basa l'obiettivo |
|---|---|---|---|---|
| Salvare una casella del registro | 0,40 s | 1,2–1,5 s | **sotto 0,05 s** a video | il salvataggio sul server dura 70–130 ms misurati; la casella si aggiorna subito e la conferma arriva dopo (stima) |
| Aprire il registro di una struttura | 0,81 s | 2,1 s | **sotto 0,3 s** (sede 0,6 s) | stima: dati compatti, niente ridisegni inutili, file statici già in memoria |
| Cambiare mese nel registro | 0,40 s | 1,2 s | **sotto 0,15 s** | stima: il mese vicino viene preparato prima del clic |
| Pagina iniziale di amministrazione, HR, direzione | 1,8–10 s | — | **sotto 0,3 s** | prototipo misurato: i totali di 60 strutture si leggono in 3 ms |
| Statistiche, apertura (6 mesi, tutte le strutture) | 17,5 s | — | **sotto 0,3 s** | prototipo misurato: 12 mesi × 60 strutture in 35 ms |
| Statistiche, 12 mesi, tutte le strutture | 29,9 s | — | **sotto 0,3 s** | come sopra |
| Da completare (tutte le strutture) | 2,2 s | — | **sotto 0,4 s** | stima: letture in blocco e 200 voci per volta |
| Archivio documenti (tutte le strutture) | 3,3 s | — | **sotto 0,3 s** | stima: 100 righe per volta |
| Personale di gruppo (3000 persone) | 0,6–0,8 s, più 0,3–0,5 s per ogni lettera cercata | — | **sotto 0,2 s**, ricerca sotto 0,05 s | stima: 200 righe per volta, ricerca su dati già pronti |
| Copertura turni di una struttura | 1,0–1,1 s | — | **sotto 0,15 s** | stima: confronto in un passaggio solo |
| Avvio o F5 del portale | 17 richieste | 17 richieste | **3 richieste** | stima: file statici in memoria del browser per un anno, nome cambiato a ogni versione |
| Aprire il manuale nel portale | 11,6 MB a ogni apertura | circa 7 s a 10 Mbit/s (stima) | **sotto 0,5 s** | stima: testo di circa 25 KB compressi, immagini caricate solo quando servono |
| 150 utenti collegati, momento di punta | non misurato | — | 95% delle risposte **sotto 0,3 s** | da misurare a fine lavori con `strumenti/carico_http.py` |

Le altre 17 pagine del portale si aprono già in 45–180 ms e restano come sono. Controlli e chiusura (0,3 s) migliora con la consegna 1.

## 2. Dove si perde il tempo oggi

1. **Il registro si ricarica e si ridisegna per intero dopo ogni casella.** Dopo un salvataggio il browser riscarica tutto il mese della struttura: 885 KB, 2086 registrazioni da 22 campi. Poi ricostruisce 6200 caselle e 15.800 elementi della pagina. Il salvataggio vero dura 70 ms; il resto, circa 330 ms in rete locale e oltre 1 s in sede, è ricarica e ridisegno. Lo stesso succede cambiando la causale nella tavolozza o filtrando.
2. **Le pagine di gruppo ricalcolano tutto a ogni apertura**, riga per riga in Python. Statistiche, Riepilogo, Da completare e Copertura leggono decine di migliaia di righe e le sommano una per una. In più, quando due di queste richieste capitano nello stesso processo, si ostacolano: le due richieste della pagina iniziale impiegano 1,7 s ciascuna da sole e **10 s insieme**. È l'«effetto convoglio» di Python: ogni riga letta da SQLite rilascia e riprende il blocco dell'interprete e aspetta l'altro thread. Misurato sul servizio: 9,4–10,2 s in tutte le 5 prove in cui le due richieste finivano nello stesso processo, 1,8 s quando finivano su processi diversi.
3. **Le liste grandi vengono disegnate tutte insieme.** Documenti: 6000 righe, 4 MB, 114.000 elementi. Da completare: 1,9 MB, 44.800 elementi, e all'avvio viene chiesto due volte solo per mostrare un numero nel menu. Personale di gruppo: 33.000 elementi, ridisegnati a ogni lettera digitata.
4. **Rete e avvio.** Ogni F5 rifà 17 richieste, perché ogni file del portale chiede al server se è cambiato. Nessuna pagina tiene in memoria i dati appena visti, quindi tornare indietro riscarica tutto. Il servizio comprime solo se davanti c'è Caddy; su Windows o dietro un proxy aziendale il registro viaggia intero, 885 KB invece di 72 KB.

Cosa **non** è un problema, misurato: SQLite (registro letto in 8 ms, 170–340 salvataggi al secondo senza errori), il costo fisso di una richiesta (5 ms per una chiamata semplice, 1 ms per un file statico), la serializzazione JSON (6 ms per il registro), la compressione (3,4 ms per comprimere il registro da 825 a 76 KB).

## 3. Il piano, in sei consegne

Ogni consegna si può mettere in esercizio da sola. Ognuna termina con le prove automatiche verdi, il giro dell'interfaccia dei 5 profili, la misura prima e dopo con gli stessi strumenti e, se cambia l'aspetto di una pagina documentata, manuale e videoguide rigenerati. I giorni sono giorni/persona e comprendono le prove.

### Consegna 1 — Il registro diventa istantaneo (circa 9 giorni)

Per chi: compilatori e responsabili, cioè chi usa il portale tutti i giorni. È la consegna con l'effetto più visibile.

- **Casella aggiornata subito.** Al clic la casella mostra la nuova causale in pochi millisecondi. Il salvataggio parte in sottofondo e il server risponde con la registrazione salvata, la riga di riepilogo della persona, i contatori e gli avvisi del mese. Il browser aggiorna solo quelle parti. Se il server rifiuta, la casella torna com'era con il messaggio d'errore. «Annulla» resta. (2 giorni)
- **Niente ridisegni completi.** Tavolozza, gomma, filtri, ricerca e «Solo da completare» cambiano solo le caselle o le righe interessate. Un solo ascoltatore di clic per tutta la griglia invece di 6200. Via il testo a comparsa ripetuto su ogni casella; resta la descrizione per i lettori di schermo. La tabella usa larghezze fisse, così il browser non ricalcola l'impaginazione di 200 righe × 36 colonne. Il ridisegno completo resta solo per cambio di mese, vista o struttura. (2,5 giorni)
- **Dati compatti e versione del mese.** Il registro scarica solo i campi che la griglia usa: circa 270 KB invece di 885, 61 KB compressi. Ogni struttura e mese ha un numero di versione che cresce a ogni modifica. Se il browser ha già quella versione, il server risponde «non cambiato» senza ricalcolare né rispedire nulla. (1,5 giorni)
- **Memoria fra le pagine e mese vicino preparato.** Tornando al registro da Controlli e chiusura la griglia compare subito e si aggiorna in sottofondo se serve. Il mese precedente e quello successivo vengono preparati quando il puntatore si avvicina alle frecce. Le richieste superate da un clic più recente vengono annullate. (1 giorno)
- **Controlli e chiusura ed Esportazioni.** Controlli e chiusura oggi scarica il registro intero senza usarne le registrazioni. Lo riscarica dopo ogni azione, anche a ogni «Registra» del carico pazienti, cioè 50–80 volte al mese per struttura. Ogni volta perde la posizione e riporta giorno e fascia all'inizio. Avrà una risposta leggera, senza registrazioni (circa 80 KB invece di 885), e aggiornerà sul posto la riga dei pazienti, passando da solo alla fascia successiva. Esportazioni scarica il registro solo per leggere un permesso, che passerà nel profilo dell'utente. (2 giorni)

Risultato atteso: salvataggio sotto 0,05 s a video, apertura sotto 0,3 s, cambio mese sotto 0,15 s.

### Consegna 2 — Configurazione del servizio (circa 1 giorno)

Si può fare subito, in parallelo alla consegna 1.

- **Intervallo di commutazione di Python a 1 ms** nel servizio. Misurato: pagina iniziale con le due richieste nello stesso processo da 9,4 a 6,3 s; 4 registri aperti insieme da 1,8 a 1,0 s. Una riga di codice. Attenua il convoglio; lo elimina la consegna 3. (0,25 giorni)
- **L'aggiornamento di «ultima attività» non aspetta mai.** Una volta al minuto per utente una pagina di sola lettura registra l'attività della sessione, cioè fa una scrittura. Se in quel momento l'archivio è occupato, oggi la pagina aspetta. Con la correzione l'aggiornamento si salta e si rifà alla richiesta successiva. (0,5 giorni)
- **Caddy con `encode zstd gzip`** nel file di esempio, e nella guida di installazione la regola che il proxy deve comprimere le risposte; `WR_PROCESSES` 2–4 è già documentato. (0,25 giorni)
- *Facoltativo, solo se l'azienda usa un proxy che non comprime:* compressione nel servizio stesso per le risposte oltre 1 KB, esclusi i percorsi della sessione. Registro 885 → 76 KB in 3,4 ms. Con Caddy non serve. (1 giorno)

### Consegna 3 — Riepiloghi pronti per le pagine di gruppo (circa 8 giorni)

Per chi: amministrazione, HR, direzione, responsabili di più strutture.

- **Tabella di riepilogo persona × mese**: per ogni persona e mese, turni, minuti, assenze, riposi, giorni lavorati, fuori sede, festivi, pianificati e quelli ancora senza consuntivo. Si aggiorna nella stessa transazione di ogni salvataggio, eliminazione, importazione o cambio di regole: misurato **0,07 ms** in più per salvataggio. Al primo avvio della nuova versione si costruisce in **4,2 s** per 1,26 milioni di registrazioni, dopo la copia di sicurezza automatica che il portale già fa prima di aggiornare l'archivio. Il ruolo valido alla data, oggi letto dai contratti, entra nella chiave del riepilogo. (2,5 giorni)
- **Statistiche lette dal riepilogo.** Prototipo misurato: 12 mesi × 60 strutture in **35 ms** contro 29,9 s, 1 mese in **3 ms** contro 3,3 s. Risultati identici al calcolo attuale, zero differenze su 3 strutture × 12 mesi. La pagina si apre subito con i filtri e carica i numeri dopo. (1,5 giorni)
- **Riepilogo di gruppo, Da completare e coda approvazioni** leggono totali e conteggi dal riepilogo e dalle letture in blocco di fascicoli, attività e scadenze: una query per tabella invece di 3–13 per persona. Il contatore del menu chiede solo i numeri, una volta sola e non due. La pagina iniziale riceve le prime 8 voci, non 1,9 MB. (1,5 giorni)
- **L'impronta dell'approvazione diventa il numero di versione** della consegna 1. Oggi serializza e firma tutte le registrazioni del mese, circa 40 ms per struttura; con il numero di versione il confronto è immediato. (1 giorno)
- **Copertura turni in un passaggio solo.** Oggi confronta ogni turno con tutti quelli della stessa persona e per le assenze rilegge i parametri del mese: decine di migliaia di query. Lo rifà dopo ogni salvataggio nella pagina, circa 1,2 s ogni volta. La nuova versione calcola gli orari una volta, legge i contratti in blocco e scorre i turni in ordine. (1 giorno)
- **Un clic dal Riepilogo apre direttamente il registro.** Oggi, cliccando una struttura o una voce di «Da completare», il portale ricalcola prima la pagina di partenza (circa 3,6 s di lavoro del server e 1,9 MB) e solo dopo apre il registro. (0,5 giorni)

Risultato atteso: pagina iniziale, statistiche e Da completare sotto 0,3–0,4 s, e nessun convoglio, perché non resta più nessuna richiesta pesante.

### Consegna 4 — Liste grandi (circa 5,5 giorni)

- **Documenti**: 100 righe per volta con «Mostra altri 100». Filtri e conteggi per stato calcolati dal server. Dopo una verifica cambia solo la riga, invece di riscaricare l'archivio. (2 giorni)
- **Personale di gruppo**: ricerca con mezzo secondo di attesa sulla digitazione, testo di ricerca preparato una volta, 200 righe per volta. (0,75 giorni)
- **Da completare**: 200 voci per volta, filtri senza ridisegnare l'elenco intero. (1 giorno)
- **Formati di numeri e date preparati una volta** invece che a ogni cella: nella scheda «Persone» delle statistiche sono 18.000 formattazioni, circa 0,2–0,35 s. (0,5 giorni)
- **Statistiche**: si aprono sulla struttura scelta in alto invece che su tutte. Si corregge anche il filtro persona, che oggi resta impostato quando si cambia struttura e produce un errore. (0,5 giorni)
- **Annullamento delle richieste superate** in Statistiche e Documenti, dove oggi una risposta lenta e vecchia può sostituirne una nuova. (0,75 giorni)

### Consegna 5 — Avvio, file del portale e manuale (circa 4,5 giorni)

- **File statici con la versione nell'indirizzo** e conservati dal browser per un anno. Ogni nuova versione del portale cambia l'indirizzo, quindi non si vede mai un file vecchio. Non serve un passaggio di compilazione, perché i moduli si importano con percorsi relativi. Al F5 le richieste scendono da 17 a 3. (1,5 giorni)
- **Moduli principali annunciati subito** nella pagina d'ingresso, così il browser li chiede tutti insieme invece che a catena. (0,25 giorni)
- **Sessione e profilo in una sola chiamata** all'avvio, e modulo della pagina caricato in parallelo. (0,5 giorni)
- **File statici serviti dalla memoria** senza rileggerli dal disco per rispondere «non cambiato». Video e manuale vengono serviti a pezzi, senza copia temporanea. (0,25 giorni)
- **Manuale leggero nel portale.** «Leggi nel portale» e il collegamento al manuale nel pannello «?» scaricano ogni volta 11,6 MB, perché le 52 schermate sono dentro il file come testo. Le immagini già compresse non si comprimono, quindi passano circa 8,7 MB anche con Caddy: circa 7 s a 10 Mbit/s, più centinaia di millisecondi di pagina ferma. Il generatore salverà le schermate come file separati caricati solo quando si scorre fino a loro. Il testo scende a circa 25 KB compressi e si scaricano solo le immagini della sezione aperta. (1 giorno più la rigenerazione del manuale)
- **Una connessione al database riusata per ogni thread** invece di tre aperte e chiuse a ogni richiesta. Su Linux il risparmio è di 1–1,5 ms per richiesta; su Windows con antivirus probabilmente di più, ma non è stato misurato. (1 giorno)

### Consegna 6 — Allegati fuori dall'archivio e guardia permanente (circa 9 giorni)

- **Allegati in un archivio SQLite separato** (scelta del titolare del 1° novembre 2026), indirizzati per impronta SHA-256. Nell'archivio principale restano solo i metadati. Le pagine di documenti e fascicoli smettono di attraversare i PDF per leggere data e autore: archivio documenti misurato da 234 a 72 ms. Il backup giornaliero dell'archivio principale torna sotto 1 GB l'anno e gli allegati si copiano solo quando sono nuovi. Procedimento completo, rivisto da due revisori indipendenti, in `ALLEGATI_ARCHIVIO_SEPARATO.md`. Si può anticipare da sola, prima dell'installazione aziendale. (7 giorni)
- **Guardia della velocità.** Un nuovo strumento, `strumenti/misura_velocita.py`, ripete le misure di questo piano su un archivio da 3000 dipendenti: browser in rete locale e in sede simulata, pagine principali, salvataggio, carico con molti utenti. Si ferma con un errore se un obiettivo della tabella §1 non è rispettato. Si aggiungono prove automatiche che contano le query per pagina, per esempio «il registro non supera N query», così una regressione si vede subito. Entra nei controlli dopo ogni modifica, insieme alle prove e al giro dell'interfaccia. (2 giorni)

## 4. Tempi e ordine

| Settimane | Consegna | Per chi cambia |
|---|---|---|
| 1–2 | 1 (registro istantaneo) e 2 (configurazione) | compilatori e responsabili: salvataggio e navigazione istantanei |
| 3–4 | 3 (riepiloghi pronti) | amministrazione, HR, direzione: pagina iniziale, statistiche, Da completare, copertura |
| 5 | 4 (liste grandi) | HR: documenti, personale di gruppo |
| 6 | 5 (avvio, file, manuale) | tutti: F5, primo accesso, guida |
| 7–8 | 6 (allegati e guardia) | backup, pagine HR, misura permanente |

| Consegna | Giorni/persona |
|---|---|
| 1 · Registro istantaneo | 9 |
| 2 · Configurazione del servizio | 1 (più 1 facoltativo) |
| 3 · Riepiloghi pronti | 8 |
| 4 · Liste grandi | 5,5 |
| 5 · Avvio, file del portale e manuale | 4,5 |
| 6 · Allegati e guardia della velocità | 9 |
| Rigenerazione di manuale e videoguide dove cambia l'aspetto | 1 |
| **Totale** | **circa 38**, cioè 7–8 settimane di una persona |

Le consegne 1 e 2 da sole, circa 10 giorni, danno già il salto più grande per chi compila ogni giorno.

## 5. Regole per restare veloci

Valgono da qui in avanti per ogni modifica, e la guardia della consegna 6 le controlla.

1. Una pagina di una struttura risponde dal server in meno di 100 ms; una pagina di gruppo in meno di 300 ms.
2. Le pagine di gruppo non leggono righe grezze di più mesi: leggono i riepiloghi.
3. Dopo una modifica si aggiorna solo ciò che è cambiato, mai la pagina intera.
4. Nessuna lista disegna più di 200 righe per volta.
5. Nessuna risposta d'uso quotidiano supera 100 KB compressi.
6. Ogni nuova pagina entra nello strumento di misura con il suo obiettivo.

## 6. Cosa il piano non fa, e perché

- **Non cambia database.** SQLite legge il registro in 8 ms e regge 170–340 salvataggi al secondo; PostgreSQL non accorcerebbe nessuno dei tempi della tabella §1, che dipendono da calcoli in Python, dalla forma dei dati e dai ridisegni (`DIMENSIONAMENTO_ARCHIVIO.md` §8).
- **Non riscrive il portale** in un altro linguaggio o con un framework per l'interfaccia. I tempi misurati si recuperano con interventi mirati sul codice esistente. Una riscrittura costerebbe mesi e rifarebbe da capo prove, manuale e video.
- **Non tocca la demo pubblica** se non per guadagnarci: il riepilogo persona × mese è una tabella SQLite e funziona anche nel browser con Pyodide.

## 7. Rischi e come si controllano

| Rischio | Controllo |
|---|---|
| Il riepilogo persona × mese diverge dalle registrazioni | aggiornamento nella stessa transazione; comando di ricostruzione completa (`manage.py check` lo confronta con un ricalcolo); prova automatica che confronta riepilogo e calcolo riga per riga dopo salvataggi, eliminazioni, importazioni e cambi di regole |
| La casella aggiornata subito mostra un valore che il server poi rifiuta | la casella torna al valore precedente con il messaggio d'errore; prova Playwright dedicata (`strumenti/prova_registro.cjs`) |
| Il browser mostra file vecchi dopo un aggiornamento | la versione è nell'indirizzo: un file cambiato ha sempre un indirizzo nuovo |
| La compressione espone il token di sessione ad attacchi noti | esclusi i percorsi di sessione; il token anti-falsificazione resta nell'intestazione, non nel corpo delle pagine compresse |
| La migrazione allo schema 2 su un archivio grande | copia di sicurezza automatica prima dell'aggiornamento, già presente; costruzione del riepilogo misurata in 4,2 s su 1,26 milioni di righe |

## 8. Prima di partire

Il piano è pronto da eseguire, ma due scelte spettano all'azienda:

1. **Ordine delle consegne.** Il piano parte da chi usa il registro tutti i giorni. Se la priorità è la direzione, la consegna 3 può passare prima.
2. **Allegati fuori dall'archivio**: deciso il 1° novembre 2026, archivio SQLite separato (`ALLEGATI_ARCHIVIO_SEPARATO.md`). Restano da fissare la conservazione dei backup e il periodo di attesa prima di cancellare i contenuti non più usati.

Le misure vanno ripetute sul server aziendale prima e dopo, con gli stessi strumenti: questi tempi vengono da un contenitore Linux con 4 CPU, non dalla rete reale delle sedi.
