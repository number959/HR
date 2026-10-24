# Conservazione e rollback

La revisione 0.8.1 conserva anche `rollback/Presenze_Web_v0.8_Originale.zip`: è lo ZIP ricevuto dall’utente, senza modifiche. L’impronta è inclusa nel nuovo `SHA256SUMS.txt`. Il suo contenuto è nella cartella `Presenze_Web_v0.8/`. La 0.8.1 non modifica lo schema SQLite né introduce migrazioni: mantenere comunque copie coerenti di codice, archivio e chiave seguendo la procedura sottostante.

Questo archivio unico contiene in `rollback/` le copie originali del codice **0.7** e **0.6**, non i database operativi. Nessun database dell'organizzazione è stato fornito o modificato in questa revisione.

| File | SHA-256 |
|---|---|
| `Presenze_Web_v0.7_Rollback.zip` | `8e971d17377330927589a855fdad5ac46617251f3b0a8ed6e9c7bb497de19682` |
| `Presenze_Web_v0.6_Rollback.zip` | `cc899cdb99ab0743899e9bce9e6c80131b473be4fb7e738ee66af4755814b60f` |

## Ripristinare solo l'interfaccia

Scegliere **Stile → Attuale**. Il cambio è immediato e non modifica dati o permessi. La 0.8 mantiene anche Spazio di lavoro, Essenziale ed Editoriale.

## Ripristinare codice e archivio

Prima di aggiornare conservare codice precedente, backup SQLite verificato, chiave 2FA originale e configurazione del servizio. Gli allegati HR sono dentro SQLite; la chiave esterna non lo è.

1. Fermare il servizio e sospendere le scritture delle sedi.
2. Conservare anche un backup della versione corrente con la sua configurazione, distinto dal backup precedente. Serve a recuperare le modifiche avvenute dopo l'aggiornamento.
3. Estrarre il codice da ripristinare in una directory distinta. Usare una directory dati pulita e copiarvi il backup corrispondente con nome `presenze.sqlite3`.
4. Collegare il servizio a quella directory e alla chiave 2FA corrispondente. Installare le dipendenze previste dalla versione scelta.
5. Eseguire `manage.py after-restore` con i percorsi corretti, secondo `INSTALLAZIONE_WEB.md`: invalida sessioni, attivazioni e codici di recupero del backup. TOTP degli account attivi resta utilizzabile con la chiave originale.
6. Riavviare e verificare accesso 2FA, autorizzazioni, un fascicolo, un allegato e un mese di presenze prima di riaprire alle sedi.

Ripristinare il vecchio database esclude le modifiche successive a quel backup: confrontarle con la copia corrente conservata e recuperarle separatamente. Non avviare la 0.6 sull'archivio aggiornato dalla 0.7/0.8: la vecchia validazione può scartare i nuovi campi HR quando si salva. La 0.8 non introduce modifiche allo schema SQL rispetto alla 0.7; usare comunque codice e backup coerenti nella procedura di ritorno.

Il ripristino di database, allegato e accesso 2FA con la chiave corretta è coperto dai test in ambiente temporaneo. Non è stato eseguito un rollback su un server dell'organizzazione.
