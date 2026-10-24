# Ripristino della versione 0.11

Prima dell’aggiornamento conservare programma, intera cartella dati, chiave privata e configurazione del servizio. Il primo avvio della 0.11 crea una copia preventiva del database prima di aggiungere le tabelle dello schema 8.

Per tornare alla 0.10, fermare il servizio e conservare separatamente tutti i dati correnti. Estrarre `rollback/Presenze_Web_v0.10_Rollback.zip` in una cartella distinta e ripristinare il backup precedente all’aggiornamento insieme alla sua chiave. Eseguire `manage.py after-restore` con il codice ripristinato prima di riaprire il servizio; confrontare gli invii con lo storico del fornitore email. Non avviare il vecchio codice sull’archivio schema 8: non gestisce approvazioni, verifiche documentali, promemoria, coperture e uscite.

Per ripristinare un backup mantenendo la 0.11, eseguire il relativo `manage.py after-restore`: revoca sessioni e recuperi, disabilita SMTP e promemoria, sospende i messaggi pendenti o in lavorazione. Le email già accettate dal server non si annullano ripristinando un backup. Verificare lo storico esterno prima di riabilitare gli invii.

Il ripristino di una copia precedente esclude le modifiche successive: conservarle e concordarne il recupero. La password SMTP e la chiave 2FA sono esterne al database e richiedono custodia separata. Le precedenti procedure sono in `qa/history/`.
