# Dimensionamento dell'archivio — SQLite con 3000 dipendenti

Domanda: *«Saranno inseriti almeno 3000 dipendenti: SQLite andrà bene o serve un altro database?»*

Risposta breve: **SQLite va bene**, con un'unica installazione su un server. Nelle prove con un archivio fittizio di 3000 dipendenti e un anno di presenze il database non è mai stato il collo di bottiglia: le pagine di una struttura rispondono in meno di un decimo di secondo e 8 compilatori che salvano insieme non producono errori. I limiti veri emersi sono due e **non dipendono dal database**: il processo Python unico, che rallenta quando molte persone aprono pagine pesanti nello stesso istante, e alcune pagine di gruppo che ricalcolano tutto in Python. Il primo si risolve con l'opzione `--processes` (aggiunta e misurata); il secondo con ottimizzazioni del codice elencate sotto, alcune già fatte. Cambiare database oggi costerebbe settimane e non risolverebbe nessuno dei due.

Tutto ciò che segue è stato misurato il 30 ottobre 2026 in un contenitore Linux con 4 CPU virtuali, Python 3.13.5, SQLite 3.45.1, disco locale. Dati fittizi. Gli strumenti per ripetere le misure sono `strumenti/carico_archivio.py` (archivio di prova e misure del motore) e `strumenti/carico_http.py` (servizio web reale con 1 o più processi).

## 1. L'archivio di prova

| Contenuto | Quantità |
|---|---|
| Strutture | 60 (50 dipendenti ciascuna) |
| Dipendenti | 3000 |
| Mesi di presenze | 12 su tutte le strutture (novembre 2025 → ottobre 2026); 60 mesi su 3 strutture per vedere l'effetto dello storico |
| Registrazioni | 1.261.865 (di cui 40.500 pianificate), una al giorno per persona con assenze e riposi |
| Righe di giornale (audit) | 1.221.365 (una per registrazione, come fa il portale) |
| Allegati | 6000 PDF fittizi da 120 KB (2 per persona), incomprimibili come una scansione |
| Dimensione del file | **1.524 MB**: allegati 707 MB, registrazioni 457 MB (≈360 byte l'una, indici compresi), giornale 358 MB (≈290 byte l'una), persone 1,3 MB |
| Tempo di caricamento con SQL diretto | 45 s |

Crescita attesa con 3000 dipendenti: circa **0,7–0,8 GB l'anno** fra registrazioni e giornale, cioè 8 GB in dieci anni. SQLite regge file di decine di GB senza cambiare comportamento; il problema della dimensione riguarda il backup, non le pagine (vedere §6).

## 2. Letture: tempi di risposta del motore

Chiamate dirette al motore (stesso codice del servizio web, senza rete), mediana di 3 ripetizioni dopo una di riscaldamento. «Prima» è il codice del mattino del 30 ottobre, «dopo» include le correzioni di §5.

| Pagina | Prima | Dopo | Dimensione risposta |
|---|---|---|---|
| Registro di una struttura (50 persone, mese corrente) | 79 ms | **45 ms** | 885 KB |
| Registro di una struttura con 5 anni di storico | 105 ms | **57 ms** | 890 KB |
| Registro di un mese chiuso di un anno fa | 75 ms | — | 602 KB |
| Persone di una struttura, elenco strutture | 3–4 ms | — | 7–13 KB |
| Fascicoli di una struttura | 11 ms | — | 15 KB |
| Archivio documenti di una struttura | 8 ms | — | 67 KB |
| Collaboratori e compensi | 88 ms | — | 1 KB |
| Anteprima paghe di una struttura | 56 ms | — | 53 KB |
| Foglio mensile Excel di una struttura | 369 ms | — | 102 KB |
| Copertura turni di una struttura | 1,19 s | — | 49 KB |
| Personale di gruppo (3000 persone) | 77 ms | — | 1,1 MB |
| Archivio documenti di tutte le strutture (6000 allegati) | 344 ms | — | 4,0 MB |
| Promemoria (tutte le strutture) | 4 ms | — | 13 KB |
| Uscite (tutte le strutture) | 23 ms | — | 446 KB |
| Coda approvazioni del mese (60 strutture) | 2,24 s | **2 ms** | 12 KB |
| Riepilogo di gruppo del mese (60 strutture) | 4,29 s | **1,92 s** | 23 KB |
| Riepilogo di gruppo in Excel | 4,51 s | ≈2 s | 11 KB |
| Da completare del mese (tutte le strutture) | 1,71 s | 1,65 s | 1,9 MB |
| Statistiche: 1 mese, tutte le strutture | 3,09 s | 3,31 s | 1,5 MB |
| Statistiche: 12 mesi, una struttura | 0,43 s | — | 42 KB |
| Statistiche: 12 mesi, tutte le strutture | **29,9 s** | invariato | 1,8 MB |

Dove va il tempo delle pagine lente (profilo con cProfile):

- **Statistiche su 12 mesi e tutte le strutture**: 49,5 s sotto profiler, di cui **zero misurabile dentro SQLite**. Il tempo è tutto in Python: 1,06 milioni di righe trasformate in dizionari e sommate una per una (6,4 milioni di chiamate alla funzione che aggiorna i contatori, 4,85 milioni di calcoli di durata). Per confronto, la stessa somma fatta dal database (`GROUP BY struttura, mese, tipo`) impiega **1,7 s**, e la semplice estrazione delle 1,06 milioni di righe 8,4 s. Il rimedio è far fare le somme a SQL, non cambiare database: PostgreSQL restituirebbe le stesse righe e Python farebbe lo stesso lavoro.
- **Riepilogo di gruppo**: 5,3 s sotto profiler, di cui 0,8 s in SQLite (1086 query) e il resto in Python: 257 mila registrazioni lette e trasformate due volte per ogni struttura (riepilogo + impronta dell'approvazione). Con la correzione dell'impronta (§5) la pagina è scesa a 1,9 s; il resto si recupera leggendo le registrazioni una volta sola o sommando in SQL.
- **Copertura turni**: confronto in Python di ogni turno con tutti quelli della stessa persona, con 5 query per coppia quando c'è un'assenza (rilievo confermato dall'audit del codice, §7). Costo fisso per mese, indipendente dal database.

Il filtro del mese usava `day LIKE 'AAAA-MM-%'`: SQLite in quel caso usa l'indice solo per la struttura e scorre tutte le righe di tutti gli anni. Sulla struttura con 5 anni di storico (85.652 righe) la query durava 22 ms contro 9 ms con un intervallo di date; corretto in tutto il motore (`months.bounds`). Non era un difetto di SQLite: nemmeno PostgreSQL usa l'indice per un LIKE con la collazione predefinita.

## 3. Scritture: più compilatori insieme

Compilatori che salvano una casella del registro alla volta nella propria struttura, come nella realtà.

| Prova | Risultato |
|---|---|
| 8 compilatori per 20 s, motore nello stesso processo | **3420 registrazioni salvate, 170 al secondo**, 0 errori, 0 «database locked»; p50 9,9 ms, p95 188 ms, max 3,3 s |
| 4 compilatori in 4 processi separati | **342 al secondo**, p50 2,6 ms, p95 6,6 ms, 0 «locked» |
| 4 compilatori + 4 lettori in 8 processi | scritture 103/s (p50 4,5 ms); letture del registro p50 127 ms, p95 219 ms |

Per riferimento, 60 compilatori che salvano una casella ogni 3 secondi producono 20 scritture al secondo: il lucchetto unico di scrittura di SQLite (una transazione per volta) ha quindi un margine di oltre dieci volte. Lo stesso discorso vale per la seconda prova, in cui le scritture sono arrivate da processi diversi: in modalità WAL più processi sullo stesso file su disco locale funzionano correttamente.

## 4. Il vero limite: un solo processo Python

Questa è la misura più importante della giornata.

| Scenario (apertura del registro di una struttura) | Tempo per risposta |
|---|---|
| 1 lettore | 65 ms |
| 4 lettori contemporanei, **thread nello stesso processo** | **3,7 s** |
| 4 lettori contemporanei, **4 processi separati** | **64 ms** |
| 8 lettori in 8 processi (4 CPU) | 137 ms |
| 4 compilatori + 4 lettori, thread | letture 4,75 s, scritture 18/s |
| 4 compilatori + 4 lettori, processi | letture 127 ms, scritture 103/s |

Stessa macchina, stesso database, stesso codice: la differenza è solo fra thread e processi. Python esegue un solo thread per volta (il «GIL»); quando più richieste lavorano insieme nello stesso processo si rubano il tempo a vicenda e ognuna si allunga di decine di volte. Il database non c'entra: con i processi separati SQLite serve 4 letture in parallelo nel tempo di una.

Conferma con il **servizio web vero** (Waitress, 8 thread per processo, client in processi separati, `strumenti/carico_http.py`):

| Processi del servizio | 1 lettore | 6 lettori insieme | 6 lettori + 2 compilatori |
|---|---|---|---|
| **1** (comportamento di prima) | 95–98 ms | **7,3 s** per risposta (1,1 aperture/s) | letture 8,8 s; scritture 13,5/s (p95 195 ms) |
| **4** (`--processes 4`) | 93 ms | **147 ms** (p95 275 ms, 38 aperture/s) | letture 217 ms (p95 398 ms); scritture 105/s (p95 52 ms) |

Zero errori in tutte le prove; sessioni e token anti-falsificazione, che stanno nel database, funzionano fra processi diversi. Da qui l'opzione **`--processes N`** (variabile `WR_PROCESSES`): il processo principale apre la porta, avvia N processi di lavoro che accettano dalla stessa presa, tiene per sé backup e promemoria e riavvia un processo che si ferma. Predefinito 1 (nessun cambiamento), consigliato 2–4 su un server Linux con più CPU. Su Windows manca `fork`: resta un processo (adatto a poche decine di utenti contemporanei). Dettagli in `INSTALLAZIONE_PASSO_PASSO.md` §2.6 bis.

Quanti utenti contemporanei aspettarsi: i 3000 dipendenti sono **record**, non utenti. Chi entra nel portale sono compilatori e responsabili (uno o due per struttura, 60–150 persone) più HR e direzione. Il momento critico è la mattina, quando molti aprono il registro insieme: con 4 processi il servizio regge 38 aperture al secondo del registro, cioè tutte le 60 strutture nello stesso paio di secondi.

## 5. Correzioni fatte il 30 ottobre 2026

Tutte coperte dalle 159 prove automatiche (5 nuove) e dal giro dell'interfaccia.

1. **Filtro del mese con intervallo di date** (`months.bounds`) al posto di `LIKE`, in registro, promemoria, approvazioni, carico pazienti, cambio regole e importazione Excel: l'indice viene usato per intero e il tempo non cresce con gli anni di storico (registro con 5 anni: 105 → 57 ms).
2. **Impronta dell'approvazione calcolata solo quando serve** (mese inviato in approvazione): il riepilogo di gruppo è passato da 4,3 a 1,9 s, la coda approvazioni da 2,2 s a 2 ms, e ogni apertura del registro risparmia la serializzazione di tutte le registrazioni del mese.
3. **Ultimo aggiornamento di struttura** nel riepilogo letto dall'ultima riga di giornale per id (indice esistente) invece di `max(at)`, che scorreva tutto il giornale della struttura.
4. **Controllo della sessione in sola lettura**: prima ogni richiesta, anche solo per aprire una pagina, prendeva il lucchetto di scrittura per aggiornare «ultima attività». Ora la sessione si aggiorna al massimo una volta al minuto. Nella prova con 6 lettori e 2 compilatori il tempo di salvataggio p95 è sceso da 377 a 195 ms con un processo e da 90 a 52 ms con quattro.
5. **Apertura dei documenti fuori dal lucchetto**: il PDF viene letto e verificato in lettura; solo la riga di giornale è una scrittura brevissima.
6. **File WAL contenuto** (`journal_size_limit` 64 MB su ogni connessione) e **manutenzione oraria** (`wal_checkpoint(TRUNCATE)` + `PRAGMA optimize`) nel pianificatore del servizio, dopo il backup.
7. **Risposta chiara quando l'archivio è occupato**: se una scrittura attende il lucchetto oltre 15 s il portale risponde 503 «Archivio momentaneamente occupato: nessuna modifica salvata. Riprovare tra qualche secondo» invece di un errore 500 generico.
8. **Anteprima dell'importazione Excel su disco** (cartella `import_pending` accanto all'archivio, 15 minuti, massimo 6) invece che in memoria: necessario con più processi, perché la conferma può arrivare a un processo diverso da quello che ha letto il file.
9. **`--processes` / `WR_PROCESSES`** nel servizio e nella console (`manage.py serve`), con prove delle opzioni e della presa condivisa.

## 6. Allegati e backup: il punto da decidere

Gli allegati (PDF) stanno dentro il database, nella stessa tabella dei loro metadati. Funziona ed è semplice da salvare, ma con 3000 persone domina tutto il resto:

| Scenario | Dimensione allegati | Backup giornaliero (copia intera a ≈80 MB/s misurati) |
|---|---|---|
| Prova: 2 PDF da 120 KB a persona | 0,7 GB | 1,5 GB in 18,6 s; controllo di integrità 9,6 s |
| 6 PDF da 1 MB a persona | 18 GB | ≈4 minuti e **18 GB di spazio al giorno** (i backup locali non vengono mai cancellati) |
| Limiti attuali del portale (200 documenti da 6 MB a persona) | fino a 3,6 TB teorici | non praticabile |

Conseguenze già visibili nel codice (audit §7): ogni pagina che elenca documenti legge colonne che stanno *dopo* il contenuto nella riga, quindi SQLite percorre le pagine del PDF anche solo per mostrare data e autore del caricamento; il backup copia ogni giorno tutti gli allegati anche se non è cambiato nulla.

Scelta consigliata per la prossima versione, da fare **prima** di caricare gli allegati di 3000 persone: tenere nel database solo i metadati e salvare i file su disco (`data/documenti/<impronta>`), nominati con l'impronta SHA-256 che il portale già calcola. Il backup dell'archivio torna a 1 GB l'anno, gli allegati si copiano in modo incrementale (solo i nuovi) con gli strumenti di sistema o la seconda copia esistente, e l'integrità si verifica per impronta. In alternativa più semplice, un secondo file SQLite solo per i contenuti. In entrambi i casi serve una migrazione dei documenti già caricati, con copia di sicurezza prima.

Da aggiungere insieme: una **conservazione dei backup locali** (per esempio ultimi 14 giornalieri + 12 mensili) e un comando di **archiviazione degli anni chiusi** (registrazioni, mesi, giornale) in un file separato di sola lettura, utile anche per i dipendenti usciti.

## 7. Audit indipendente del codice

Tre revisori automatici indipendenti hanno letto il motore con tre lenti (interrogazioni, concorrenza e operatività, crescita e manutenzione) e un verificatore scettico per lente ha controllato ogni rilievo sul codice, correggendo le stime. Rilievi confermati e stato:

| Rilievo | Dipende dal database? | Stato |
|---|---|---|
| Filtro del mese con LIKE che ignora l'indice sui giorni | no | **corretto** |
| Impronta SHA-256 di tutto il mese ricalcolata a ogni riepilogo, coda e apertura del registro | no | **corretto** (calcolata solo con mese in approvazione) |
| `max(at)` sul giornale senza indice adatto nel riepilogo di gruppo | no | **corretto** |
| Ogni richiesta prendeva il lucchetto di scrittura per la sessione | in parte | **corretto** |
| Lettura dei documenti dentro il lucchetto di scrittura | in parte | **corretto** |
| Nessun limite al WAL, nessun `optimize` | in parte | **corretto** |
| Errore 500 generico quando il lucchetto è occupato | no | **corretto** (503 con messaggio) |
| Anteprima importazione Excel in memoria di un solo processo | no | **corretto** (su disco) |
| Statistiche: 12–24 mesi sommati in Python (30–45 s di CPU per tutte le strutture) | no | **da fare**: somme in SQL (misurate: 1,7 s) e limite a 12 mesi su «tutte le strutture» |
| Copertura turni: confronto quadratico con 5 query per coppia (1,2 s per struttura, fino a 5–8 s con più pianificato) | no | **da fare**: intervalli calcolati una volta, contratti letti in blocco |
| «Da completare», statistiche HR e promemoria: 3–13 query per persona | no | **da fare**: letture per struttura in blocco |
| Esportazioni Excel di gruppo caricano tutte le registrazioni anche per i prospetti che non le usano | no | **da fare** |
| Allegati come BLOB: file di decine di GB copiato per intero ogni giorno, colonne dopo il BLOB | no (PostgreSQL attenuerebbe solo la lettura delle colonne) | **da decidere** (§6) |
| Backup locali mai cancellati, copia intera prima di ogni importazione Excel dentro la richiesta | no | **da fare**: conservazione; copia asincrona |
| Giornale e storici crescono senza limite (0,4–0,5 GB l'anno) | no | **da fare**: archiviazione per anno |
| Promemoria: scansione di tutto il personale ogni 5 minuti dentro una transazione di scrittura (0,4–1 s) quando posta e promemoria saranno attivi | in parte | **da fare**: calcolo in lettura, scrittura breve |
| Con più processi, il lucchetto dei backup e lo stato `backup_status.json` non sono condivisi fra processi | no | **documentato**: backup pianificato solo nel processo principale; il backup manuale dal portale può sovrapporsi a quello pianificato (due copie valide) |

Il quarto agente, incaricato dell'inventario dei costrutti SQLite, si è fermato per il limite orario dell'account: l'inventario di §8 è stato fatto a mano con ricerche sul codice.

## 8. E se un giorno servisse PostgreSQL?

Quando avrebbe senso: più server applicativi in alta disponibilità, replica verso un'altra sede, un database centrale interrogato anche da altri programmi (contabilità, paghe), hosting in cloud con database gestito, oppure centinaia di scritture al secondo continuative. Nessuna di queste condizioni è nel perimetro attuale (un server aziendale, 60–150 utenti).

Cosa costerebbe (conteggi sul codice del 30 ottobre):

| Elemento | Quantità | Lavoro |
|---|---|---|
| Istruzioni SQL (`execute`/`executemany`) | 326 in 26 moduli | segnaposto `?` → `%s` (292 righe), revisione di ogni query |
| `INSERT OR REPLACE` / `OR IGNORE` | 28 | riscrivere con `ON CONFLICT` |
| Indici parziali, `CHECK`, `AUTOINCREMENT`, `COLLATE NOCASE`, `strftime`/`datetime` | 4 + 17 + 4 + 5 + 8 | tradurre schema e funzioni |
| API `sqlite3` (connessioni, `backup()`, `Row`, transazioni, PRAGMA) | 15 usi + 12 PRAGMA | riscrivere `wr/db.py`, `wr/backups.py` (backup = `pg_dump`), `manage.py` (`check`, `after-restore`) |
| Prove automatiche | 159, ognuna con un archivio SQLite temporaneo | nuovo fixture su database di prova |
| Migrazione dalla 0.11 | legge due archivi SQLite | resta SQLite in lettura, scrive su PostgreSQL |
| **Demo nel browser (Pyodide)** | usa SQLite dentro il browser | **non può usare PostgreSQL**: si dovrebbero mantenere due database o rinunciare alla demo senza server |
| Installazione | — | servizio PostgreSQL, utenti e password, backup, aggiornamenti: un componente in più da gestire in azienda |

Stima onesta: **10–15 giorni/persona** per migrare mantenendo le prove verdi, più il doppio binario per la demo. In cambio non si otterrebbe alcun miglioramento sulle misure di questo documento: le pagine lente resterebbero lente (Python), il limite dei thread resterebbe (si risolve con i processi, non con il database) e il lucchetto unico di scrittura, l'unico vero vantaggio di PostgreSQL, oggi lavora al 10% della sua capacità.

## 9. Cosa fare, in ordine

1. **Subito, nell'installazione**: server Linux con 2–4 CPU, disco SSD locale, `WR_PROCESSES=2` (4 oltre i 100 utenti), backup locali su disco con spazio per almeno due settimane di copie.
2. **Prima di caricare gli allegati di tutti**: decidere la sede degli allegati (§6) e la conservazione dei backup.
3. **Prossima versione**: statistiche con somme in SQL, copertura turni senza confronto quadratico, letture in blocco per «Da completare» e promemoria, esportazioni senza registrazioni superflue, archiviazione degli anni chiusi.
4. **Ripetere le misure** sul server reale con `strumenti/carico_archivio.py` e `strumenti/carico_http.py` prima dell'avvio: i tempi qui sono di un contenitore a 4 CPU, non del server aziendale.

## 10. Limiti di queste misure

Dati sintetici con distribuzione regolare (una registrazione al giorno per persona); nessun HTTPS né reverse proxy davanti al servizio; client e server sulla stessa macchina; nessuna misura su disco di rete o virtuale lento, dove il costo di ogni commit (fsync) sarebbe più alto. L'audit del codice è una lettura statica verificata da un secondo revisore, non una prova eseguita su ogni rilievo.
