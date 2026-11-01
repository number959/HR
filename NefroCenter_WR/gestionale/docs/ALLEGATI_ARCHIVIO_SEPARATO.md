# Allegati in un archivio separato — come si fa

Scelta del titolare (1° novembre 2026): il contenuto degli allegati (PDF, immagini) passa dall'archivio principale `wr.sqlite3` a un **secondo archivio SQLite** `wr_allegati.sqlite3`, nella stessa cartella dei dati. Nell'archivio principale restano solo le informazioni sugli allegati: nome, tipo, scadenza, dimensione, impronta, chi e quando. **Non è ancora realizzato nel portale.**

Il procedimento è stato provato su una copia dell'archivio fittizio da 3000 dipendenti (6000 allegati da 120 KB) in un contenitore Linux con 4 CPU. Poi è stato rivisto da due revisori indipendenti, uno sui punti del codice da toccare e uno sul funzionamento di SQLite. Hanno trovato 16 problemi, uno in comune, tutti recepiti in questa versione; una prova ha confermato quello sulla numerazione (§7).

## 1. Com'è fatto

| | Archivio principale `wr.sqlite3` | Archivio allegati `wr_allegati.sqlite3` |
|---|---|---|
| Contiene | tutto il portale; per ogni allegato nome, categoria, scadenza, tipo, dimensione, impronta SHA-256, caricamento, verifiche | solo i contenuti: una riga per impronta con dimensione, data di arrivo e byte del file |
| Cresce | circa 0,7–0,8 GB l'anno con 3000 dipendenti | quanto i documenti caricati |
| Si modifica | a ogni operazione | aggiungendo righe; cancella solo con la pulizia ritardata (§5) |

Il legame fra i due archivi è l'**impronta SHA-256** del file, che il portale calcola già oggi. Lo stesso file caricato due volte occupa spazio una volta sola. Ogni lettura ricalcola l'impronta: un file alterato viene rifiutato, come oggi.

```sql
-- archivio allegati, creato con PRAGMA auto_vacuum=INCREMENTAL prima della tabella
CREATE TABLE contents(
  id INTEGER PRIMARY KEY AUTOINCREMENT,   -- non riusa mai un numero
  sha256 TEXT NOT NULL UNIQUE,            -- legame con documents.sha256
  size INTEGER NOT NULL,
  stored_at TEXT NOT NULL,
  orphan_since TEXT NOT NULL DEFAULT '',  -- da quando nessun documento usa più questo contenuto
  content BLOB NOT NULL);                 -- ultima colonna: le altre si leggono senza attraversare il file
CREATE TABLE quarantine(                  -- contenuti già alterati trovati durante l'aggiornamento (§4)
  document_id TEXT PRIMARY KEY, declared_sha256 TEXT NOT NULL, actual_sha256 TEXT NOT NULL,
  found_at TEXT NOT NULL, content BLOB NOT NULL);
-- archivio principale, schema 2: documents senza la colonna content, più
CREATE INDEX documents_sha256 ON documents(sha256);
```

Nel codice nasce un modulo `wr/attachments.py` con cinque operazioni: *salva*, *leggi* con verifica, *controlla* (documenti senza contenuto), *pulisci* e *copia per il backup*. Le pagine del portale non cambiano aspetto.

## 2. Le quattro regole di sicurezza

1. **Mai una transazione su due archivi.** In modalità WAL una transazione che scrive due file collegati non è atomica, e SQLite conferma per primo l'archivio principale. Quindi ogni operazione usa due connessioni separate: prima si scrive e si conferma il contenuto nell'archivio allegati, con scrittura sicura su disco, poi si scrive l'archivio principale. Un'interruzione può lasciare al massimo un contenuto senza documento, che la pulizia toglie. Un documento senza contenuto non può nascere.
2. **L'archivio allegati non si crea mai per sbaglio.** Si apre solo se esiste; lo creano soltanto l'installazione, l'aggiornamento di schema, la migrazione dalla 0.11 e la costruzione della demo. Se manca, il servizio non parte e spiega perché. Oggi invece SQLite creerebbe un file vuoto, e tutti i documenti diventerebbero illeggibili in silenzio.
3. **Un contenuto si cancella solo con la pulizia**, tenendo il lucchetto dell'archivio allegati e ricontrollando l'archivio principale in quel momento (§5).
4. **Ogni copia dell'archivio principale ha la sua copia degli allegati**, fatta subito dopo: anche le copie prima di un aggiornamento, di un'importazione Excel o dalla console (§6).

## 3. Le operazioni quotidiane

- **Caricamento.** Prima i controlli in lettura: permesso, persona, fascicolo, limite di 200 documenti, formato. Poi *salva* nell'archivio allegati, che toglie anche un eventuale segno di pulizia sullo stesso contenuto. Infine il documento nell'archivio principale, con i controlli ripetuti nella stessa scrittura. Il lucchetto preso dal PDF è quello dell'archivio allegati: misurato 48 ms per un PDF da 6 MB, durante i quali registro e presenze continuano a salvare.
- **Apertura e scaricamento.** Dati del documento dall'archivio principale, contenuto dall'archivio allegati per impronta: 0,13 ms per 120 KB, verifica compresa; per 6 MB circa 10 ms di verifica (stima). La riga di giornale resta nell'archivio principale.
- **Eliminazione.** Si cancella il documento dall'archivio principale. Il contenuto resta finché la pulizia non lo toglie, così un ripristino recente ritrova i suoi file.
- **Pagine di documenti e fascicoli.** Leggono solo l'archivio principale, senza file dentro: archivio documenti di tutte le strutture **da 234 a 72 ms**, fascicoli di una struttura da 6 a 3 ms.

## 4. Aggiornare un archivio che contiene già allegati (schema 2)

**Quando parte.** Solo all'avvio del servizio o con un comando esplicito, `manage.py aggiorna-archivio`. Gli altri comandi della console, per esempio `backup` o `activate`, trovando lo schema vecchio si fermano e chiedono di aggiornare: oggi invece aggiornerebbero da soli, anche con il servizio vecchio ancora acceso. Un file di blocco nella cartella dei dati impedisce due aggiornamenti contemporanei e un servizio acceso durante l'aggiornamento.

**Passi**, con i tempi misurati per 6000 allegati (707 MB):

| Passo | Tempo | Se si interrompe |
|---|---|---|
| 1. Copia di sicurezza completa dell'archivio, con la sua copia degli allegati (§6). Se esiste già una copia dello stesso archivio non modificato, si riusa | 18 s | nulla è cambiato |
| 2. Creazione dell'archivio allegati e copia dei contenuti a blocchi di circa 100 MB, verificando l'impronta di ognuno. Un contenuto già alterato oggi va in quarantena con un avviso, senza fermare l'aggiornamento | 9 s | l'archivio principale non è toccato; al riavvio si riprende dai contenuti mancanti |
| 3. In una sola transazione dell'archivio principale: si ricontrolla la versione dello schema, si copiano gli eventuali contenuti arrivati nel frattempo, si verifica che ogni documento abbia il suo contenuto o sia in quarantena, si conta quante verifiche dei documenti ci sono, si toglie la colonna (`ALTER TABLE documents DROP COLUMN content`, SQLite 3.35 o successivo), si ricontano le verifiche, si aggiorna la versione | 11,5 s | tutto o niente |
| 4. Compattazione dell'archivio principale, prima di aprire la porta agli utenti | 7 s | il portale funziona già; la compattazione si ripete al riavvio |

Risultato misurato: archivio principale **da 1525 a 791 MB**, archivio allegati 707 MB, zero documenti senza contenuto, relazioni integre.

Note per chi realizza:
- Il passo 3 usa `DROP COLUMN` e non la ricostruzione della tabella. Una ricostruzione cancellerebbe la tabella dei documenti, e con le chiavi esterne attive questo svuoterebbe anche le verifiche dei documenti; il conteggio prima e dopo lo controlla.
- Le migrazioni oggi sono solo istruzioni SQL in una transazione: serve il supporto a passi scritti in Python.
- Python 3.12/3.13 per Windows e le distribuzioni Linux supportate (per esempio Ubuntu 22.04 e successive, Debian 12) hanno SQLite 3.37 o successivo. Il passo 3 controlla comunque la versione e si ferma con un messaggio chiaro se è più vecchia di 3.35. La demo, con Pyodide, ha SQLite 3.39 e riceve un archivio già costruito con lo schema 2.

**Con allegati veri**, per esempio 6 PDF da 1 MB a persona, cioè 18 GB, i tempi crescono in proporzione: **stima 10–15 minuti** a servizio fermo. Spazio su disco necessario durante l'aggiornamento: la copia di sicurezza (archivio intero), il nuovo archivio allegati (quanto gli allegati) e, per la compattazione, circa due volte l'archivio principale compattato, nella cartella dei dati e nella cartella temporanea di sistema.

**Il momento migliore è prima di caricare i documenti dei dipendenti.** Il portale aziendale non è ancora installato: se questa versione arriva prima, le nuove installazioni nascono già con i due archivi e l'aggiornamento serve solo per archivi di prova. La migrazione dalla 0.11 scriverà direttamente nei due archivi, con le regole del §2.

## 5. Pulizia dei contenuti non più usati

Una volta al giorno il servizio:

1. prende il lucchetto di scrittura dell'archivio allegati;
2. legge in quel momento quali impronte usa l'archivio principale;
3. toglie il segno ai contenuti di nuovo usati e mette la data di oggi a quelli non più usati;
4. cancella i contenuti segnati da più di **N giorni** e ancora non usati;
5. libera lo spazio a poco a poco (`PRAGMA incremental_vacuum`).

Un caricamento dello stesso file durante la pulizia aspetta il lucchetto e poi toglie il segno, quindi non può perdere il contenuto.

**Regola:** N deve essere almeno pari alla conservazione dei backup dell'archivio principale, sia locali sia sul NAS, contata in giorni. Oggi i backup locali non vengono mai cancellati e quelli sul NAS si contano in numero di copie. Serve quindi una decisione sulla conservazione in giorni (§9).

Un documento eliminato su richiesta della persona resta nei backup fino alla loro scadenza: è il comportamento normale dei backup e va scritto nell'informativa.

## 6. Backup e seconda copia

Ogni backup diventa una **coppia di file che non cambiano più**:

| File | Contenuto | Tempo misurato |
|---|---|---|
| `wr_AAAAMMGG_…sqlite3` | archivio principale completo, come oggi | 10 s invece di 18 s; con 18 GB di allegati la differenza sarebbe di minuti |
| `allegati_AAAAMMGG_…sqlite3` | solo i contenuti nuovi rispetto alle copie precedenti della stessa catena | 0,32 s con 20 nuovi PDF da 1 MB; un file quasi vuoto se non ce ne sono |
| `allegati_completo_AAAAMM.sqlite3` | una copia completa degli allegati una volta al mese, che apre una nuova catena | 4,7 s per 727 MB |

- **Tutte le copie passano da un solo punto** (`backups.create`): anche quelle prima di un aggiornamento di schema, di un'importazione Excel, dalla console e all'installazione. La coppia risulta completa solo quando entrambi i file sono scritti e controllati.
- **Un file di blocco condiviso fra i processi** evita copie sovrapposte del servizio, dei processi di lavoro e della console. Oggi il lucchetto vale solo fra i thread di un processo.
- **Il backup giornaliero** controlla a parte che esistano la copia principale e quella degli allegati del giorno.
- **La verifica di una coppia** controlla l'integrità e che ogni impronta citata dalla copia principale stia nella catena degli allegati: 1,5 s. Riconosce anche le copie fatte prima dell'aggiornamento, con lo schema 1.
- **La prova di ripristino mensile** ricalcola tutte le impronte: 0,75 s per 727 MB, circa 20 s per 18 GB (stima).
- **La seconda copia sul NAS**, quando sarà configurata, copia le stesse coppie e cancella le catene di allegati quando nessuna copia principale conservata le usa più.
- **Lo scaricamento di un backup dal portale** resta per l'archivio principale. Gli allegati, che superano i limiti di un download dal browser, si prendono dal server.

## 7. Ripristino

1. Fermare il servizio e mettere da parte l'archivio allegati in uso, se esiste ancora.
2. Rimettere l'archivio principale del giorno scelto, in una cartella pulita, senza vecchi file `-wal` o `-shm`.
3. Ricostruire l'archivio allegati con un nuovo comando: copia completa del mese più le copie giornaliere fino al giorno scelto. Si aggiungono anche i contenuti dell'archivio messo da parte, così non si perde nulla di più recente.
4. `manage.py after-restore`, come oggi. In più azzera i segni di pulizia, esegue *controlla* e impedisce la ripartenza se anche un solo documento è senza contenuto, indicando quali.

`manage.py check` mostrerà sempre lo stato dell'archivio allegati: integrità, contenuti, documenti senza contenuto (devono essere zero), quarantena, contenuti in attesa di pulizia.

**Perché ogni backup è un file nuovo e non una copia unica aggiornata ogni giorno.** La prima versione di questo progetto prevedeva una sola copia cumulativa, aggiornata copiando le righe con numero più alto dell'ultimo copiato. Una prova ha confermato il rischio indicato dai revisori. Senza AUTOINCREMENT, SQLite riassegna a un file nuovo il numero di un contenuto appena cancellato, e quella copia lo saltava. Inoltre un file unico modificato da più processi non ha storico e può corrompersi tutto insieme.

## 8. Cosa cambia nel codice

| Parte | Modifica |
|---|---|
| `wr/attachments.py` (nuovo) | archivio allegati: salva (toglie il segno di pulizia), leggi con verifica, controlla, pulisci, copia per il backup; apertura senza creazione, con il percorso ricavato da quello dell'archivio principale |
| `wr/schema.py`, `wr/db.py` | schema 2; passi di migrazione in Python; file di blocco; copia «prima dell'aggiornamento» fatta tramite `backups.create` e riusata se già presente |
| `wr/app.py`, `wr/server.py` | all'avvio: aggiornamento se serve, poi *controlla*; il servizio non parte se l'archivio allegati manca; pulizia giornaliera nel pianificatore |
| `wr/hr.py` | caricamento con controlli prima del salvataggio, apertura ed eliminazione con le regole del §2 |
| `wr/backups.py` | coppie di file, catene mensili, file di blocco fra processi, controllo giornaliero dei due file, verifica di schema 1 e 2, prova di ripristino, seconda copia e potatura sul NAS |
| `wr/excel_import.py` | copia prima dell'importazione tramite `backups.create` |
| `manage.py` | `aggiorna-archivio` (nuovo), `ricostruisci-allegati` (nuovo, per il ripristino), `check` con lo stato degli allegati; `after-restore` con i nuovi controlli; gli altri comandi non aggiornano lo schema; `init`, `migra-011` e `demo-data` rifiutano una cartella che contiene già un archivio allegati |
| `wr/migrate011.py` | contenuti scritti per primi, con connessione separata; controllo finale «nessun documento senza contenuto»; in caso di errore cancella anche l'archivio allegati che ha creato |
| `wr/sample.py`, `demo/` | i dati di prova creano i due archivi; la costruzione della demo prepara e firma anche il secondo file, `demo-main.js` e `ponte.py` lo caricano |
| prove automatiche | caricamento, apertura, eliminazione, stesso file in due documenti, interruzione fra i due passi, pulizia in gara con un caricamento dello stesso file, aggiornamento interrotto a ogni passo e con un allegato già alterato, archivio allegati mancante, coppie di backup e catene, ripristino con ricostruzione, migrazione dalla 0.11 interrotta |
| documenti | installazione (spazio su disco, conservazione, ripristino), verifica, manuale (pagina Backup) |

**Stima: circa 7 giorni/persona**, prove comprese. La prima stima era 4 giorni; la revisione ha aggiunto le regole di sicurezza, le coppie di backup e il ripristino guidato. È la parte «allegati» della consegna 6 del piano di velocità (`PIANO_VELOCITA.md`) e si può anticipare da sola.

## 9. Decisioni che servono all'azienda

1. **Conservazione dei backup in giorni**, locali e sul NAS. Da essa discende il periodo di attesa N prima di cancellare un contenuto non più usato. Proposta: 90 giorni per entrambi.
2. **Spazio su disco del server**: archivio principale, allegati, copie complete mensili e giornaliere per il periodo di conservazione. Per l'aggiornamento di un archivio già pieno serve in più circa la dimensione degli allegati più due volte l'archivio principale (§4).
3. **Quando farlo**: consigliato prima dell'installazione aziendale, così non serve aggiornare dati reali.
