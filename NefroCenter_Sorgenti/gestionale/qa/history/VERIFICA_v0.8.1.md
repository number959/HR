# Verifica di Persone e Presenze Web 0.8.1

Revisione del 18 ottobre 2026. Collaudo locale Linux con archivi temporanei e dati fittizi; nessuna installazione o pubblicazione aziendale. Le verifiche 0.8 ricevute sono conservate in `qa/history/VERIFICA_v0.8.md`, con i rispettivi log. Non sono confuse con gli esiti di questa sessione.

## Provenienza e integrità

Archivio ricevuto: `NefroCenter_Presenze_Web_v0.8_Passaggio_Codex.zip`, 1.372.033 byte. SHA256: `0b2cc8da2352ec1ae7a3aa4550de7927f989302f83479adceb0ba7bd9f786d10`. CRC dello ZIP valido e tutte le **155 impronte** del manifest originale corrispondenti. La copia ricevuta è conservata senza modifiche in `rollback/Presenze_Web_v0.8_Originale.zip`.

## Risultati di questa revisione

- Suite iniziale: **95 test Python superati**.
- Suite dopo le correzioni: **98 test Python superati**, in 52,692 secondi. Log: `qa/unit-tests.log`.
- Percorso browser della consegna: superato contro Waitress reale, inclusi attivazione 2FA, recupero, permessi del compilatore, HR, allegati, presenze, accordi, statistiche, sei file Excel e backup.
- **Percorso browser finale 0.8.1 superato**, incluse tutte le nuove regressioni e i controlli preesistenti. Log: `qa/browser-tests.log`.
- Sintassi Python/JavaScript e `git diff --check`: superati.

## Nuove regressioni Python

1. **Tipi Excel HR:** ore settimanali numeriche e part-time percentuale con due decimali; virgola italiana accettata; matricola e CAP testuali con zeri iniziali; campi mancanti vuoti. Valori e formato verificati leggendo direttamente OOXML con la libreria standard.
2. **Backup giornaliero:** directory, collegamenti simbolici, file parziali, nomi estranei e contenuti senza intestazione SQLite non impediscono la creazione della copia. Dopo una copia valida non viene prodotta una seconda copia automatica dello stesso giorno.
3. **Console dopo ripristino:** `manage.py after-restore` revoca sessioni, recuperi e attivazioni; preserva il secondo fattore TOTP dell’account attivo e permette la rigenerazione dei recuperi. Le prove preesistenti verificano anche dati HR, allegati, chiave corretta ed errore con chiave errata.

## Browser e controllo visivo

Le prove usano quattro stili e larghezze di 1400, 1024, 390 e 320 pixel. Le tabelle ampie mantengono lo scorrimento interno; il controllo automatico verifica l’assenza di overflow della pagina nei percorsi eseguiti. Le schermate di Statistiche e Backup ed esportazioni sono state ispezionate visivamente su desktop e telefono.

Le regressioni aggiunte riguardano esportazioni dopo cancellazione dei mesi e cambio del tipo di prospetto, filtro ruolo inesistente nel nuovo centro e apertura HR dopo il cambio di centro dalla dashboard. Nessuna presenza del centro secondario viene aggiunta per alterare il totale dimostrativo di sei ore.

Il confronto dei quattro stili è in `anteprime/CONFRONTO_STILI_v0.8.1.md`. Le immagini derivano dal servizio reale con dati dimostrativi, non dalla simulazione storica 0.7. Non includono credenziali operative.

## Ambiente e risorse

Python 3.12.14, cryptography **50.0.2** installata in ambiente virtuale isolato secondo `requirements.txt`; Node.js 24.19.0; Playwright 1.62.1; Chromium di sistema **154.0.8037.57**. Il browser del contenitore di prova è stato avviato con `--no-sandbox`; questo non modifica la configurazione dei browser degli utenti.

Nessuna nuova dipendenza di produzione o libreria grafica. Conservati XlsxWriter 3.2.9 (BSD-2-Clause), Waitress 3.0.2 (ZPL-2.1), PyOTP 2.9.0 (MIT), Segno 1.6.6 (BSD-3-Clause), cryptography 50.0.2 (Apache-2.0 oppure BSD-3-Clause), Roboto locale (OFL-1.1), Lucide (ISC con attribuzione Feather MIT), CSS e JavaScript nativi. Licenze della consegna mantenute; logo del gruppo invariato.

## Limiti ancora validi

Nessun collaudo sul server aziendale, Windows, rete fra sedi, HTTPS reale, telefono fisico per il QR o carico di produzione. Nessun audit indipendente. Gli XLSX sono verificati come OOXML e scaricati nel browser, senza apertura in Excel desktop.

Il filtro dei backup controlla nome, tipo di file e intestazione SQLite: non effettua una nuova verifica completa delle copie già conservate. L’integrità completa resta verificata alla creazione. Backup automatici ancora locali, senza rotazione o replica remota; chiave 2FA da conservare separatamente. Database HR e allegati non sono cifrati integralmente dall’applicazione.

Restano anagrafiche distinte per centro e statistiche per ruolo attuale. Gli accordi importati non diventano approvati. Excel originale e video non sono stati forniti o riletti: i riscontri Sodav restano quelli documentati nel pacchetto precedente.

Il pacchetto di consegna esclude database e download dimostrativi del collaudo, chiavi temporanee, ambienti virtuali, cache e repository Git. Include codice, test, log, guide, licenze, anteprime selezionate e rollback. `SHA256SUMS.txt` descrive i file della nuova consegna.
