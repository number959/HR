# Configurare le comunicazioni email — 0.10

Il fornitore di posta non è ancora definito. Gli invii reali sono disattivati; modelli, liste, anteprime e bozze funzionano senza SMTP. Nessuna email è stata inviata durante il collaudo: il trasporto è stato sostituito da simulazioni nei test.

## Parametri per il tecnico

Usare **Comunicazioni → Servizio di posta**, con un account amministratore e secondo fattore recente. Il salvataggio della configurazione non invia messaggi.

- Server: nome host SMTP comunicato dal fornitore, senza prefisso `https://` o porta nel nome.
- Porta e sicurezza: TLS diretto oppure STARTTLS obbligatorio, con verifica del certificato. Usare i valori del proprio fornitore; non è previsto trasporto in chiaro.
- Nome utente: account autorizzato a spedire. Può restare vuoto solo per un relay aziendale che autorizza il server senza autenticazione; TLS resta obbligatorio.
- Password: il tecnico imposta `PRESENZE_SMTP_PASSWORD` nell’ambiente del servizio. Non inserirla nella rubrica, nei modelli, nei file del progetto o nei comandi condivisi. Non viene salvata nel database né restituita dall’API.
- Mittente, nome visualizzato e indirizzo di risposta: usare recapiti autorizzati dal servizio aziendale.
- Email per lotto: da 1 a 20. Limite orario globale: da 1 a 2000 tentativi; anche gli errori e i lotti già presi in carico consumano il limite.

La compatibilità va verificata con il tecnico. Sono supportati SMTP con TLS e credenziali oppure un relay autorizzato; OAuth2 e API proprietarie dei singoli fornitori non sono integrate. Non si presume che qualsiasi casella Microsoft 365, Gmail o PEC accetti questa modalità. La PEC è un dato della rubrica, non un canale di spedizione certificata implementato dal gestionale.

Il server deve poter raggiungere l’host e la porta SMTP configurati. La demo statica pubblica non usa SMTP e non può spedire email reali. Dopo la configurazione aziendale, effettuare una prova concordata con un indirizzo autorizzato e controllare lo storico del fornitore.

## Come funziona l’invio

HR e amministratori preparano lista e testo, generano l’anteprima, leggono anomalie e destinatari e salvano una bozza immutabile. Una conferma successiva avvia un lotto preciso. La conferma è legata ai destinatari, ai tentativi già registrati e alla configurazione: richieste ripetute o obsolete vengono rifiutate, senza avanzare al lotto successivo.

Ogni email ha un solo destinatario e nessun CC/BCC condiviso. I documenti HR non vengono allegati. Il contenuto è testo semplice, con campi personalizzati esplicitamente ammessi. L’accettazione SMTP non è conferma di consegna o lettura; non sono integrati tracking o elaborazione dei rimbalzi.

**Errore**: il messaggio non è stato accettato dal server secondo la risposta osservata. Dopo avere corretto la causa, usare **Riprova solo gli errori** e confermare di nuovo. **Esito incerto**: l’invio potrebbe essere stato accettato prima della perdita di connessione. Non viene ritentato; verificare il servizio di posta prima di preparare eventualmente una nuova comunicazione.

Se il processo si interrompe, lo storico può mostrare un lotto in corso. Dopo almeno 15 minuti senza aggiornamenti del lotto, **Verifica invio interrotto** classifica le richieste abbandonate come incerte, senza spedire nulla. I destinatari mai presi in carico restano disponibili per una nuova conferma. Non ripetere una campagna da un’altra scheda per aggirare uno stato in corso.

## Backup e ripristino

Bozze e storico sono nel database e quindi nei backup. La password SMTP è esterna al database e va gestita separatamente dal tecnico. Dopo un ripristino eseguire `manage.py after-restore`: disabilita SMTP e sospende gli invii pendenti. Confrontare gli ultimi invii con i log del fornitore prima di abilitare nuovamente la posta e creare nuove bozze: un backup precedente potrebbe non registrare email già spedite successivamente.
