# Passare dalla 0.11 (Persone e Presenze Web) a NefroCenter WR

La migrazione **crea un nuovo archivio WR** a partire da una copia dell'archivio della 0.11. L'archivio 0.11 non viene toccato: la vecchia installazione resta utilizzabile finché non si decide di spegnerla.

## Cosa serve

- Una **copia di backup** dell'archivio 0.11 (`presenze.sqlite3`), fatta a servizio fermo o con la pagina Backup della 0.11.
- La **chiave del server della 0.11** (`server.key`), se si vuole che le app Authenticator già configurate continuino a funzionare. Senza chiave la migrazione riesce lo stesso, ma chi usava l'app riceve un nuovo codice di attivazione.
- Una cartella dati **nuova** per WR (`--data-dir`): se contiene già un archivio, la migrazione si ferma.
- La chiave del server WR (`--key-file`): se non esiste viene creata.

## Comando

Dalla cartella `gestionale`, con l'ambiente virtuale di WR:

```bash
.venv/bin/python manage.py migra-011 \
    --source /percorso/copia/presenze.sqlite3 \
    --legacy-key /percorso/chiave-0.11/server.key \
    --data-dir /var/lib/nefrocenter-wr --key-file /etc/nefrocenter-wr/server.key
```

Il comando:

1. apre la copia 0.11 **in sola lettura** e ne controlla struttura e integrità (serve uno schema 0.11, versione 8 o successiva);
2. crea il nuovo archivio WR e vi scrive tutto **in una sola transazione**: o entra tutto, o niente;
3. confronta i conteggi (strutture, persone, registrazioni, documenti, account) e controlla l'integrità del nuovo archivio;
4. fa un backup «dopo-migrazione-011» e scrive il rapporto `migrazione-011.json` nella cartella dati (senza segreti);
5. stampa i codici di attivazione per le persone che devono ricollegare l'app Authenticator (solo senza `--legacy-key`, o per attivazioni già in corso).

## Cosa viene conservato

| Nella 0.11 | In WR |
|---|---|
| Strutture, parametri per periodo, festività, sedi esterne | Strutture con lo storico dei parametri (una versione per ogni cambiamento) |
| Persone, matricole, contratti, personale di gruppo | Persone e identità di gruppo (stessa persona in più strutture) |
| Registro presenze (consuntivo e pianificato), orari, sedi, festivi, note | Registrazioni con sorgente e segnalazioni «da verificare» conservate |
| Mesi chiusi, verificati, approvazioni, riaperture | Stato del mese e percorso di approvazione, con le impronte ricalcolate |
| Fascicoli HR, attività di inserimento, documenti con contenuto, verifiche documentali | Fascicoli, inserimento, documenti (impronta ricalcolata) e verifiche |
| Accordi e calcoli del mese | Accordi (modello a turni, ore o fisso) |
| Sostituzioni, uscite e dotazioni, paghe, storico | Copertura, uscite e dotazioni, paghe, registro delle attività |
| Account, ruoli, strutture assegnate, password, codici di recupero, attivazioni in corso | Identici: le password e i codici di recupero continuano a funzionare |
| App Authenticator | Conservata con `--legacy-key`; altrimenti nuovo codice di attivazione |
| Configurazione della posta e dei promemoria | Importata ma **spenta**: va ricontrollata e riattivata a mano |

Tutto ciò che la migrazione non riesce a interpretare con certezza viene segnalato nel rapporto e, dove possibile, lasciato «da verificare» nel portale (per esempio le registrazioni importate da Excel nella 0.11 con sede o colore non riconosciuti).

## Dopo la migrazione

1. Avviare il servizio WR e fare il primo accesso con un amministratore (stessa password e stesso secondo fattore, oppure il nuovo codice di attivazione stampato).
2. Controllare qualche struttura e qualche mese chiuso confrontandoli con la 0.11 (registro, fascicoli, documenti).
3. Riconfigurare la seconda copia dei backup, la posta e i promemoria, che arrivano spenti.
4. Spegnere la 0.11 solo quando le sedi lavorano sulla WR. Per tornare indietro basta riaccendere la 0.11 sul suo archivio, che non è cambiato (le modifiche fatte nel frattempo in WR non vi compaiono).

## Prove eseguite

La migrazione è coperta da prove automatiche su un archivio 0.11 sintetico costruito con la stessa struttura della vecchia versione (`tests/test_migrate011.py`: origine intatta, tutto-o-niente, parametri dei mesi, sedi e importazioni, persone e fascicoli, accordi, servizi spenti, impronte, accessi con password, Authenticator e codici di recupero). È stata provata anche su un archivio generato dal codice della 0.11 (`strumenti/archivio_011_di_prova.py`). Non è stata eseguita su un archivio aziendale reale: farlo su una copia, mai sull'originale.
