# Persone e Presenze Web 0.10 — strutture e comunicazioni email

**Inizia da [AGGIORNAMENTO_0.10.md](AGGIORNAMENTO_0.10.md).** Per installare: [INSTALLAZIONE_IN_BREVE.md](INSTALLAZIONE_IN_BREVE.md). Guide, tutorial e videoguide sono disponibili anche nel portale. La demo pubblicata separatamente usa dati fittizi; il gestionale operativo richiede il server aziendale.


Per presentare il software all’ufficio HR: [PRESENTAZIONE_PER_UFFICIO_HR.md](PRESENTAZIONE_PER_UFFICIO_HR.md), disponibile anche in PDF nella demo. La schermata iniziale spiega per ciascun ruolo scopo, dati visibili, operazioni consentite, limiti ed esempio pratico.

## Novità 0.10

La rubrica **Strutture** raccoglie i dati societari, indirizzi, email HR e amministrative, PEC e referenti; ogni fascicolo mostra i recapiti aggiornati della propria struttura. Amministratori e HR centrale vedono tutte le sedi; i responsabili solo quelle assegnate.

**Comunicazioni**, per amministratori e HR centrale, aggiunge cinque modelli iniziali, liste dinamiche di dipendenti o contatti delle strutture, esclusioni, deduplicazione, anteprima personalizzata e bozze che conservano testi e destinatari verificati. L'invio richiede conferma del singolo lotto e secondo fattore recente; ogni email ha un solo destinatario. Lo storico distingue accettazione SMTP, errori ed esiti incerti: l'accettazione SMTP non prova la consegna. Le richieste ripetute non inviano automaticamente il lotto successivo. Gli invii incerti non vengono ritentati e i lotti abbandonati possono essere verificati esplicitamente dopo 15 minuti.

Il servizio di posta aziendale non è ancora stato scelto. **SMTP è disattivato inizialmente e durante lo sviluppo non sono state inviate email reali.** La configurazione richiede un amministratore, TLS e credenziali oppure un relay autorizzato; la password rimane nell'ambiente del servizio, fuori dal database. Istruzioni in [docs/SMTP_CONFIGURAZIONE.md](docs/SMTP_CONFIGURAZIONE.md). Non sono inclusi invii ricorrenti, allegati HR automatici, tracking delle letture o integrazioni OAuth/API dei singoli fornitori.

Sono incluse **30 guide per pagina, 225 riferimenti alle impostazioni e 30 videoguide illustrate senza audio**, con sottotitoli e trascrizioni. La presentazione del prodotto è un video separato; sono disponibili una versione senza audio e una con voce sintetica italiana, entrambe di 88 secondi in Full HD con sottotitoli e trascrizione. Le funzioni 0.9 comprendono HR centrale, documenti delle sedi consultabili dall'ufficio centrale, attività, identità collegate esplicitamente, decorrenze, modello paghe configurabile e backup NAS disattivati fino alla configurazione della destinazione.

Per aggiornare alla 0.10 seguire [AGGIORNAMENTO_0.10.md](AGGIORNAMENTO_0.10.md) e [ROLLBACK.md](ROLLBACK.md): l'avvio aggiorna il database allo schema 7 dopo una copia preventiva. Dopo un ripristino `manage.py after-restore` revoca gli accessi, disabilita SMTP e sospende le email pendenti con esito incerto. Il tracciato paghe del consulente, la destinazione NAS reale e il server aziendale restano da configurare e collaudare.

## Cronologia delle versioni precedenti

Le descrizioni di aggiornamento 0.8 e precedenti riportate sotto sono storiche. Per l'aggiornamento corrente usare sempre la procedura 0.10.


Revisione del 18 ottobre 2026: corretti tipi numerici negli Excel HR, campi nascosti nelle esportazioni, navigazione e filtri tra centri e riconoscimento delle copie giornaliere. Leggere [AGGIORNAMENTO_0.8.1.md](AGGIORNAMENTO_0.8.1.md) per modifiche, avvio e rollback, e [VERIFICA.md](VERIFICA.md) per il nuovo collaudo. Le sezioni seguenti conservano la descrizione delle funzionalità 0.8.

Versione web del gestionale NefroCenter, 17 ottobre 2026. Tutte le postazioni usano il browser e lo stesso archivio sul server. Non occorre installare l’EXE nelle sedi e non occorre sincronizzare cartelle con Drive o Syncthing.

**Il gestionale operativo non è stato installato su un server aziendale. La demo separata non contiene dati reali.** `INSTALLAZIONE_WEB.md` descrive configurazione, attivazione e messa in servizio. Il servizio va ospitato su un computer/server disponibile e raggiungibile dalle sedi. La soluzione non richiede abbonamenti software; hardware, connettività, gestione e disponibilità del server restano necessari.

## Novità 0.8

**Statistiche** aggiunge filtri per centro, periodo, ruolo e persona, andamento delle ore, confronti fra sedi, assenze per causale, completezza degli orari, pianificazioni senza consuntivo e riepilogo HR riservato. Le ore mancanti non vengono trasformate in zeri o stimate.

**Backup ed esportazioni** raccoglie sei prospetti Excel nativi: registro del singolo centro, presenze complessive, statistiche, fascicoli, onboarding/scadenze e accordi. I file rispettano i permessi e conservano i tipi di date, numeri e ore. L'amministratore può creare, elencare e scaricare backup completi del database con allegati. La chiave 2FA resta separata. Dettagli e sviluppi proposti in `STATISTICHE_ED_ESPORTAZIONI.md`.

Per proseguire con Codex leggere prima **INIZIA_QUI_CODEX.md**. `CONTESTO_CONVERSAZIONE.md` conserva le richieste utente disponibili e le decisioni ricostruite. Il pacchetto contiene anche le copie del codice 0.7 e 0.6 per il rollback.

## Funzioni della 0.7 conservate

Fascicolo dipendente articolato in otto sezioni: **Anagrafica, Recapiti, Contratto, Amministrazione, Qualifiche, Onboarding, Documenti e Scadenze**. Sono disponibili 53 campi standard, più i campi personalizzati del centro. I 17 campi aggiunti comprendono documento di identità e scadenza, PEC, email aziendale, partita IVA, modalità di pagamento, intestatario e banca, numero contratto, centro di costo, sede, badge e tutor. Restano la checklist configurabile, gli allegati e lo storico delle modifiche.

Dal fascicolo si aprono le presenze filtrate della persona e il suo accordo del mese selezionato. Le scadenze raccolgono dati del contratto, documenti, qualifiche e attività di onboarding. Le date mostrate derivano dai dati salvati: dopo una modifica salvare il fascicolo per aggiornarle.

Il selettore **Stile** nella testata offre tre alternative: **Spazio di lavoro**, con navigazione laterale blu; **Essenziale**, con superfici chiare e indice verticale del fascicolo; **Editoriale**, con titoli serif e tonalità più calde. **Attuale** conserva l’aspetto precedente ed è l’impostazione iniziale. La scelta è locale al browser e non modifica dati o permessi. Il ritorno ad Attuale è immediato; per tornare anche al codice precedente vedere `ROLLBACK.md`.

La revisione precedente comprendeva 77 test. La 0.8 estende le verifiche a statistiche, Excel e download dei backup. Esiti effettivi e limiti aggiornati sono in `VERIFICA.md`.

## Registro mensile e calcoli individuali

Registro mensile per fasce sul modello Sodav, con contatori e vista a sette giorni. Nuova area **Accordi e calcoli**: parametri distinti per persona, centro e mese, importazione delle formule riconosciute come proposte da confermare, modelli a turni/ore/quota fissa e modifica protetta da verifica recente con password e 2FA. Gli importi non sono esposti al compilatore. Vedere `MODELLO_SODAV.md` per differenze individuali, anomalie del file e limiti del calcolo.

## Funzioni

- Dashboard unica dei centri autorizzati: ore, turni, mesi chiusi, registrazioni mancanti, esportazione CSV.
- Registro presenze, pianificazione/consuntivo, orari, pause, causali, assenze e sedi. Parametri versionati per centro, controlli sulle sovrapposizioni, chiusura e riapertura motivata del mese.
- Archivio dipendenti con anagrafica, rapporto di lavoro, documenti, scadenze, campi personalizzati e onboarding configurabile. Conservati modello di 14 attività, allegati PDF/PNG/JPEG fino a 6 MiB e cronologia delle modifiche.
- Importazione Excel esistente; migrazione dei backup delle sedi, compresi fascicoli e allegati.
- Account nominativi, secondo fattore obbligatorio e autorizzazioni controllate dal server su ogni operazione.
- Backup SQLite verificati, automatici giornalieri e manuali; registro di attività applicative e di sicurezza.

La dashboard rilegge i dati ogni minuto e dispone di Aggiorna. Le scritture completate sono immediatamente disponibili nel database. Il registro segnala conflitti fra modifiche concorrenti e richiede di ricaricare, evitando sovrascritture silenziose. **Per compilare serve la connessione al server: non è presente una modalità offline.**

## Profili

| Profilo | Centri | Presenze e parametri | Fascicoli HR | Account |
|---|---|---|---|---|
| Amministratore | Tutti | Gestione completa | Tutti | Gestione e ripristino |
| HR centrale | Tutti | Consultazione delle presenze | Tutti, documenti centrali e comunicazioni | Nessuna gestione |
| Responsabile centro | Solo assegnati | Gestione del centro | Solo centri assegnati | Nessuna gestione |
| Compilatore | Solo assegnati | Inserimento secondo i permessi del centro; parametri non modificabili | Nessun accesso | Solo sicurezza personale |
| Direzione / lettore | Solo assegnati | Consultazione ed esportazioni | Nessun accesso | Solo sicurezza personale |

Un account Direzione con tutti i centri assegnati può consultarli insieme. I fascicoli completi ora risiedono sul server centrale: non rimangono sui PC delle sedi. Il ruolo HR centrale, disponibile dalla 0.9, gestisce il personale e i documenti di tutte le sedi senza le funzioni di amministrazione tecnica. Dalla 0.10 può inoltre gestire modelli, liste e invii email; la configurazione SMTP resta riservata all’amministratore.

## Autenticazione a due fattori

1. L’amministratore crea un account e consegna password iniziale e codice riservato di attivazione, dopo aver verificato la persona.
2. Al primo accesso l’utente inserisce il codice di attivazione, valido 7 giorni, scansiona il QR con un’app compatibile TOTP e sceglie la propria password di almeno 12 caratteri.
3. L’app richiede un codice valido prima di attivare l’accesso. Mostra 10 codici di recupero monouso da conservare separatamente da password e telefono.
4. Agli accessi successivi: nome utente e password, poi codice Authenticator. In alternativa al codice Authenticator si può usare un codice di recupero insieme alla password.

Il QR è generato direttamente dal server: il segreto non viene inviato a servizi di immagini, analytics o QR esterni. Nessun SMS o email automatica, nessun canone per il secondo fattore. La generazione del codice TOTP sul telefono funziona senza Internet; il browser deve raggiungere il portale.

La password da sola non autorizza nessuna lettura o scrittura dei dati. Non esistono account di default, registrazione pubblica, endpoint pubblico di prima configurazione o comando web che spenga il server. Tutti i ruoli devono completare il secondo fattore. Non è disponibile un comando per disattivarlo.

Da **Sicurezza · 2FA** l’utente può sostituire Authenticator, rigenerare i codici di recupero, cambiare password e terminare le altre sessioni. Le operazioni sensibili richiedono un’autenticazione completa avvenuta negli ultimi 5 minuti; altrimenti viene chiesta nuovamente password e secondo fattore. La sostituzione del dispositivo revoca vecchio segreto, recuperi e altre sessioni.

Il ripristino amministrativo del 2FA richiede una motivazione, revoca tutte le sessioni della persona e genera una nuova attivazione. La verifica dell’identità deve avvenire con la procedura dell’organizzazione: il sistema registra la motivazione ma non certifica la persona. Il reset della sola password mantiene il secondo fattore.

## Protezioni implementate

- TOTP a 6 cifre e intervalli di 30 secondi, finestra tollerata ±1 intervallo; contatore anti-riutilizzo persistente e aggiornato in transazione.
- Sessioni lato server, cookie HttpOnly, SameSite=Strict e Secure in HTTPS; scadenza per inattività di 15 minuti e durata massima 8 ore. Le verifiche incomplete durano 5 minuti.
- Token CSRF per sessione e verifica dell’origine. Cookie e token sono rinnovati dopo la password e dopo il secondo fattore. Identificativi delle sessioni conservati come hash nel database.
- Limiti persistenti sui tentativi di password, attivazione e codici. Il blocco del secondo fattore non viene azzerato iniziando una nuova verifica password.
- Segreti TOTP cifrati con Fernet; chiave esterna al database. Codici di recupero casuali conservati solo come impronte. Codici, password e segreti non sono registrati nel log di sicurezza.
- Risorse grafiche locali, script esterni al markup, CSP senza script inline, divieto di incorporamento in frame e risposte riservate non memorizzabili nelle cache.

Queste protezioni non rendono TOTP resistente al phishing e non equivalgono a un audit indipendente o a una certificazione. **Il database dei dipendenti e gli allegati non sono cifrati integralmente dall’app.** La cifratura aggiunta riguarda i segreti 2FA; occorre proteggere dischi, account del server, cartelle e backup. Chi controlla il server e la chiave può intervenire fuori dall’applicazione.

## Aggiornamento da web 0.7

Conservare il backup e la chiave originali, fermare il servizio ed estrarre il nuovo codice in una cartella distinta. Mantenere i percorsi dati e chiave: la 0.8 non modifica lo schema SQLite. XlsxWriter è incluso. Non rieseguire `manage.py init` su un archivio già configurato. Controllare accesso con 2FA, un fascicolo, un allegato, un mese di presenze, le statistiche e un download Excel. Le nuove pagine non modificano i dati durante la consultazione.

## Aggiornamento da web 0.6

Arrestare il servizio, creare e conservare un backup verificato dell’archivio con gli allegati e conservare separatamente la chiave 2FA e la configurazione. Estrarre il nuovo codice in una directory distinta, mantenendo i percorsi dati e chiave già configurati. I nuovi campi HR sono aggiunti alla lettura dei profili esistenti e non richiedono una migrazione SQL. I vecchi dati e le checklist vengono mantenuti. Non eseguire `manage.py init` su un archivio già configurato.

Dopo il riavvio controllare accesso, un fascicolo, un allegato e un mese di presenze. Il pacchetto precedente è conservato separatamente; il ripristino del codice richiede anche l’archivio corrispondente, secondo `ROLLBACK.md`. Non avviare la 0.6 sull’archivio modificato dalla 0.7: un salvataggio con la vecchia versione può eliminare i nuovi campi HR.

## Aggiornamento da web 0.5

Arrestare il servizio e conservare un backup verificato del database, degli allegati e della chiave 2FA. Sostituire i file applicativi mantenendo i percorsi dati e chiave già configurati, quindi riavviare. La nuova struttura degli accordi è contenuta nei dati dei periodi: gli archivi esistenti non richiedono una migrazione SQL. Gli accordi precedenti diventano proposte da verificare e confermare; non presumere che una vecchia simulazione sia un accordo approvato. Se il modello Sodav era già stato importato con una versione precedente, il blocco dei duplicati impedisce di reimportarlo: configurare gli accordi nell’archivio esistente.

## Installazione e migrazione

La base è Python, Waitress e SQLite locale al server, con un unico processo applicativo. Le sedi accedono tramite HTTPS, direttamente o tramite la VPN aziendale. Il database non va collocato su una cartella di rete o sincronizzata.

`migrate_desktop.py` importa un backup completo delle versioni 0.4/0.5: centri, parametri, persone, registrazioni, periodi, fascicoli, allegati e storico. Rigenera gli identificativi ed evita collisioni dei codici centro; l’importazione è atomica e il medesimo file non può essere importato due volte. Non fonde dipendenti o centri provenienti da backup diversi e non importa gli account locali: gli account web vanno creati e attivati con 2FA. Utilizzare un solo backup autorevole per ogni sede e confrontare i totali dopo la migrazione.

La checklist HR organizza le verifiche e conserva gli allegati; non invia UNILAV né produce firme digitali. Non caricare diagnosi o referti sanitari. Modelli e adempimenti devono essere adattati dai referenti competenti. Il fascicolo non sostituisce un software paghe e gli accordi non calcolano contributi, imposte o netto in busta.

## Librerie e risorse

- XlsxWriter 3.2.9, BSD-2-Clause: file Excel nativi, incluso; nessun Excel installato richiesto sul server.
- PyOTP 2.9.0, MIT: codici TOTP e indirizzi di attivazione; incluso nel pacchetto.
- Segno 1.6.6, BSD-3-Clause: QR generati localmente; incluso.
- cryptography 50.0.2, Apache-2.0 oppure BSD-3-Clause: cifratura dei segreti; versione fissata in `requirements.txt`.
- Waitress 3.0.2, ZPL-2.1: servizio HTTP dietro HTTPS; incluso.
- Roboto, OFL-1.1; Lucide Static 0.468.0, ISC con attribuzione Feather MIT; animazioni CSS native con movimento ridotto.
- Logo NefroCenter: risorsa del gruppo, non licenza open source.

Attribuzioni in `licenses/`, `assets/` e `WAITRESS-LICENSE.txt`. Provenienza e versioni in `dependencies.json`, `assets/resources.json` e `waitress_metadata.json`.
