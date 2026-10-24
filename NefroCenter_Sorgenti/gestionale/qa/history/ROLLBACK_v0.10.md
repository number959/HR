# Rollback della versione 0.10

Il codice precedente è in `rollback/Presenze_Web_v0.9_Rollback.zip`. Sono conservate anche le copie 0.8.1, 0.8 originale, 0.7 e 0.6. Prima dell'aggiornamento salvare separatamente codice, database, intera cartella dati, chiave 2FA e configurazione del servizio. Il primo avvio 0.10 crea una copia preventiva del database prima di aggiungere le tabelle dello schema 7.

Per tornare alla 0.9:

1. Fermare il servizio e conservare separatamente l'intera cartella dati 0.10, compresi documenti e storico delle comunicazioni. Non sovrascrivere questa copia.
2. Estrarre il codice 0.9 in un'altra cartella. Ripristinare in una cartella dati pulita il backup precedente all'aggiornamento, con la chiave 2FA corrispondente e la configurazione del servizio.
3. Eseguire il comando `manage.py after-restore` della versione ripristinata secondo `INSTALLAZIONE_WEB.md`, per revocare sessioni e codici di recupero del backup. Verificare accessi, fascicoli, allegati e presenze prima di riaprire il servizio.

Non avviare la 0.9 sul database modificato dalla 0.10: i dati delle strutture e le comunicazioni non sarebbero gestiti dal vecchio codice. Il ripristino della copia precedente esclude le modifiche successive; conservarle per confronto e recupero concordato. Le email eventualmente già accettate dal servizio di posta non possono essere annullate ripristinando un backup.

## Ripristino mantenendo la 0.10

Se si ripristina un backup usando ancora il codice 0.10, eseguire il relativo `manage.py after-restore` prima di riaprire il servizio. Oltre a revocare sessioni e codici di recupero, disabilita SMTP e classifica come incerti i destinatari pendenti o in lavorazione, impedendo di riprendere automaticamente invii dal vecchio archivio. Confrontare gli ultimi invii con lo storico del fornitore: il backup potrebbe non contenere email già spedite dopo la sua creazione. Riabilitare il servizio di posta solo dopo questa verifica e preparare nuove bozze per gli eventuali destinatari da contattare.

La password SMTP è esterna al database; conservare separatamente la configurazione dell'ambiente del servizio. Dettagli in `docs/SMTP_CONFIGURAZIONE.md`.

I documenti delle versioni precedenti e i relativi esiti sono conservati in `qa/history/`.
