# Comunicazioni e servizio di posta

Il servizio di posta aziendale **non è ancora stato scelto**: nel portale l'invio arriva disattivato. Modelli, liste di destinatari, anteprime e bozze funzionano lo stesso; nessuna email parte finché l'amministratore non configura e abilita il server di posta. Nella demo pubblica gli invii sono sempre simulati.

## Parametri (Comunicazioni → Server di posta, solo amministratore)

| Parametro | Note |
|---|---|
| Server e porta | nome host SMTP del fornitore (senza `https://`), porta indicata dal fornitore (predefinita 465) |
| Sicurezza | `ssl` (TLS diretto) oppure `starttls`; il certificato viene verificato; nessun invio in chiaro |
| Utente | account autorizzato a spedire; può restare vuoto solo per un relay aziendale che autorizza il server |
| Password | **non si inserisce nel portale**: il tecnico imposta la variabile `WR_SMTP_PASSWORD` nell'ambiente del servizio (`deploy/wr.env.example`) |
| Mittente e nome | indirizzo e nome visualizzati; indirizzo di risposta facoltativo |
| Email per lotto, limite orario | da 1 a 20 email per ogni conferma; da 1 a 2000 tentativi all'ora |
| Invio abilitato | si può attivare solo dopo aver indicato server e mittente |

Il salvataggio dei parametri non invia nulla. Dopo la configurazione fare una prova concordata con un indirizzo autorizzato e controllare lo storico del fornitore. Sono supportati SMTP con TLS e credenziali o un relay autorizzato; OAuth2 e API proprietarie dei singoli fornitori non sono integrate: non presumere che una casella qualsiasi accetti questa modalità.

## Come funziona l'invio

1. HR o l'amministratore scelgono un modello e una lista di destinatari (persone delle strutture o indirizzi della rubrica) e generano l'**anteprima**: ogni messaggio è visibile prima di creare la bozza.
2. La **bozza** è immutabile: elenca i destinatari e i messaggi definitivi.
3. La **conferma** (password e codice dell'app) spedisce un lotto preciso. Ogni email ha un solo destinatario, nessuna copia conoscenza, testo semplice. I documenti HR non vengono allegati.
4. Ogni destinatario ha uno stato: *Da inviare*, *In invio*, *Accettato dal server di posta*, *Non riuscito*, *Esito incerto*, *Invio simulato (demo)*. L'accettazione da parte del server non è conferma di consegna o lettura.
5. **Non riuscito**: dopo aver corretto la causa si usa «Ritenta i non riusciti». **Esito incerto**: l'invio potrebbe essere stato accettato prima di un'interruzione; non viene ritentato da solo.
6. Se il processo si interrompe, dopo 15 minuti senza aggiornamenti il pulsante **Verifica invio interrotto** classifica come incerti i destinatari rimasti «in invio», senza spedire nulla.

## Promemoria automatici

I promemoria (scadenze di contratti e documenti, inserimenti in ritardo, presenze del mese precedente da verificare) usano lo stesso servizio di posta e arrivano **spenti**. Si attivano da **Promemoria** solo dopo la posta, confermando destinatari e anteprima; il portale li controlla ogni cinque minuti e li invia all'ora scelta (fuso Europe/Rome), entro il massimo giornaliero impostato. Il server deve essere acceso a quell'ora.

## Backup e ripristino

Modelli, liste, bozze e storico sono nell'archivio e quindi nei backup. La password SMTP è fuori dall'archivio. Dopo un ripristino `manage.py after-restore` spegne posta e promemoria e segna come incerti gli invii in corso: confrontare gli ultimi invii con lo storico del fornitore prima di riabilitare.
