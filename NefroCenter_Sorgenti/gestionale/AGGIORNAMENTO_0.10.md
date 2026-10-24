# NefroCenter — aggiornamento 0.10

La versione aggiunge la rubrica delle strutture e le comunicazioni email richieste. Il servizio di posta aziendale non è ancora stato scelto: gli invii reali sono inizialmente disattivati e non sono state spedite email durante lo sviluppo.

## Rubrica delle strutture

La pagina **Strutture** contiene ragione sociale, partita IVA, codice fiscale, indirizzo, comune, CAP, provincia, telefono, email generale, email HR, email amministrazione, PEC, referente, direttore, sito e note organizzative.

Ogni fascicolo ha una sezione **Struttura di riferimento**, collegata al centro del dipendente. I dati vengono letti dalla rubrica comune: aggiornandoli una volta, tutti i fascicoli della sede mostrano i recapiti aggiornati. I dipendenti presenti in più centri conservano il riferimento del rispettivo fascicolo. La rubrica non trasferisce il dipendente fra sedi.

Amministratori e HR centrale accedono a tutte le strutture; i responsabili solo alle proprie. Compilatori e lettori non accedono alla rubrica riservata. I salvataggi controllano le versioni concorrenti e sono registrati nello storico.

## Comunicazioni email

La pagina **Comunicazioni** è riservata a HR centrale e amministratori:

- Cinque modelli iniziali modificabili: benvenuto, documenti da completare, scadenze, verifica presenze e comunicazione alla struttura. Puoi creare altri modelli e usare i campi personali elencati nella guida.
- Liste dinamiche per centri, ruoli e stato del rapporto, usando esplicitamente l’email aziendale oppure personale. Sono disponibili anche liste dei contatti generali, HR o amministrativi delle strutture. Puoi escludere singoli indirizzi.
- L’anteprima elimina i duplicati, segnala indirizzi mancanti o non validi e mostra il messaggio personalizzato per ogni destinatario. Le variabili senza un valore bloccano la creazione della bozza.
- La bozza conserva una copia dei destinatari e dei testi controllati. Modifiche successive alla rubrica o al modello non riscrivono la bozza.
- L’invio richiede una conferma esplicita e un secondo fattore recente. Ogni destinatario riceve un messaggio individuale, senza copie visibili ad altri. I lotti contengono al massimo 20 email e rispettano un limite orario configurabile.
- Lo storico distingue destinatari in attesa, in lavorazione, accettati da SMTP, falliti o con esito incerto. **Accettato da SMTP non significa consegnato o letto.** Si possono ritentare esplicitamente gli invii falliti; quelli incerti richiedono verifica e non vengono reinviati automaticamente.

Non vengono allegati automaticamente documenti dei fascicoli. Le email sono in testo semplice. Non sono stati attivati promemoria automatici né campagne ricorrenti: restano idee da valutare dopo la prova del flusso manuale.

## Configurare il servizio di posta

Solo l’amministratore configura SMTP nella pagina Comunicazioni. Servono server, porta, TLS, mittente e credenziali o un relay aziendale autorizzato. La password è conservata esclusivamente nell’ambiente del servizio tramite `PRESENZE_SMTP_PASSWORD`, senza campi password nell’interfaccia o copie nel database. Il salvataggio delle impostazioni non invia messaggi.

Il tecnico deve verificare la compatibilità del fornitore, gli indirizzi autorizzati e i limiti. Le integrazioni OAuth/API dei singoli fornitori non sono incluse automaticamente. Dettagli in `docs/SMTP_CONFIGURAZIONE.md`.

## Demo, guide e aggiornamento

Demo: https://nefrocenter-demo.icy-bass-2671.chatgpt.site. Le nuove funzioni usano dati fittizi; la spedizione è soltanto una simulazione nella scheda del visitatore. Non parte alcuna email.

Sono incluse 30 procedure, 225 riferimenti alle impostazioni e 30 videoguide illustrate senza audio, con sottotitoli e trascrizioni. Le nuove pagine hanno aiuto contestuale e tutorial.

Per aggiornare il gestionale, fermare il servizio, conservare codice, database e chiave originali ed estrarre la nuova versione in una cartella separata. L’avvio crea una copia preventiva prima di aggiungere le nuove tabelle dello schema 7. I dati preesistenti restano conservati. Le copie precedenti sono in `rollback/`; tornare alla versione precedente richiede anche il database e la chiave corrispondenti.

Dopo un ripristino eseguire `manage.py after-restore`: oltre a revocare sessioni e codici di recupero, disabilita SMTP e sospende le email pendenti con esito incerto. Confrontare lo storico del servizio di posta prima di preparare nuove bozze, perché un backup precedente potrebbe non contenere gli ultimi invii già avvenuti.

La configurazione e il collaudo del server aziendale, del NAS e del servizio di posta reale restano da completare con il tecnico.

## Materiale per la presentazione a HR

`PRESENTAZIONE_PER_UFFICIO_HR.md` descrive tutte le funzioni, il percorso sede → HR, i cinque ruoli e una scaletta per la demo. La copia PDF di sette pagine è scaricabile dalla schermata iniziale della demo, insieme alla presentazione video di 88 secondi con voce sintetica italiana o senza audio. Le schede dei ruoli distinguono scopo, ambito dei dati, azioni permesse, limiti ed esempio da provare.
