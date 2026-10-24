# Verifica di Persone e Presenze Web 0.8

Consegna del 17 ottobre 2026. Codice collaudato localmente su Linux, non pubblicato su server aziendale o Internet. I test usano dati inventati e archivi temporanei. Il rapporto precedente è conservato in `qa/history/VERIFICA_v0.7.md`.

## Esito finale

**95 test Python superati**, più il percorso end-to-end Chromium contro un servizio Waitress reale. Esiti completi: `qa/unit-tests.log` e `qa/browser-tests.log`.

| Area | Test | Esito |
|---|---:|---|
| Presenze, regole, configurazione e autorizzazioni | 25 | Superati |
| HR, onboarding, allegati e concorrenza | 13 | Superati |
| Web, 2FA, sessioni, ruoli, download e ripristino | 27 | Superati |
| Accordi individuali e riconoscimento formule | 12 | Superati |
| Migrazione atomica | 2 | Superati |
| Statistiche, denominatori, filtri e dati mancanti | 9 | Superati |
| Excel nativi e backup scaricabili | 7 | Superati |
| **Totale** | **95** | **Superati** |

Ambiente: Python 3.12.14, Node.js 24.19.0, Playwright 1.62.1, Chromium headless 155.0.8059.79. Sintassi dei file Python e JavaScript e integrità dell'archivio controllate durante il confezionamento. È un collaudo applicativo, non una certificazione o un audit indipendente.

## Verifiche aggiunte per la 0.8

- Somme delle ore con notte e pause; turni privi di orari distinguibili da zero; periodi vuoti; completezza calcolata sui conteggi complessivi, non media semplice dei centri.
- Distinti per persona/centro/giorno, fasce di assenza separate dai riposi; codici identici con significati diversi separati; pianificato risolto anche da un'assenza effettiva.
- Filtri coerenti tra totali, mesi, centri, ruoli, persone e CSV; limiti del periodo e filtro persona vincolato al centro; esclusione e segnalazione delle registrazioni orfane.
- Riepilogo HR attuale, filtrato e riservato; attività concluse/non applicabili escluse dagli arretrati; persone non attive escluse dal riepilogo attuale.
- File XLSX letti indipendentemente come OOXML con la libreria standard: fogli, valori numerici, date, ore, celle vuote e protezione dall'interpretazione di testo come formule o hyperlink. Le librerie di produzione non vengono usate per rileggere i loro stessi valori.
- Esportazioni HR e accordi negate al compilatore; centri estranei negati; revoca del permesso di export rispettata; nessun IBAN di prova negli export pubblici; importi non confermati vuoti.
- Backup integro con allegato presente, nomi validati, rifiuto di percorsi arbitrari e link simbolici, file parziali esclusi, limite download applicato. Download riservato all'amministratore con verifica recente; chiave TOTP esterna esclusa.
- Nuove rotte inaccessibili con sola password; MIME e intestazioni di download verificati; operazioni riservate richiedono password e secondo fattore recenti.

La prova di ripristino già presente nella suite continua a verificare integrità, riferimenti, rilettura HR/allegato e accesso 2FA con la chiave corretta. La chiave errata è rifiutata; `after-restore` invalida sessioni e codici secondo la procedura documentata.

## Browser e controllo visivo

Il percorso reale comprende attivazione 2FA, password personale, recuperi, creazione/modifica del dipendente, documento, onboarding, presenze, accordi, statistiche, filtri centro/ruolo/persona, assenza di dati, tutti e sei i file Excel e creazione/download del backup. La prova del compilatore conferma assenza dei prospetti privati, del pannello backup e del riepilogo HR.

Quattro stili provati a **1400, 1024, 390 e 320 pixel**: sezioni HR e nuove pagine Statistiche/Backup ed esportazioni. Verificati anche collegamenti al registro individuale, persistenza dello stile, ritorno ad Attuale, flussi su mobile, ordine da tastiera del login, assenza di errori JavaScript e violazioni CSP nel percorso collaudato. Ispezionate visivamente le nuove pagine desktop e mobile. Le tabelle e il grafico con molti mesi possono scorrere nel loro contenitore.

Il primo percorso ha rilevato un overflow della tabella backup su mobile. Corretto il dimensionamento minimo delle celle del contenitore CSS grid; il percorso completo successivo è passato a tutte le larghezze previste. I backup sono inoltre pubblicati tramite rinomina atomica solo dopo la verifica di integrità, per non esporre copie ancora in scrittura.

Le prove delle quattro anteprime storiche sono in `qa/history/v0.7-preview-tests.log`. L'HTML storico incluso è una simulazione grafica con dati fittizi, precedente alle nuove pagine; non è il servizio web reale e non implementa autenticazione di produzione.

## Modello Excel originale

Questa revisione non riesegue Excel o VBA e non include la fonte originale. Conserva il riscontro della 0.7 documentato in `MODELLO_SODAV.md` e `qa/source-check.json`: 17 anagrafiche, 231 registrazioni, 194 turni senza orari effettivi e 10/10 combinazioni riconosciute confrontate con i valori memorizzati usando il teorico della fonte. Gli accordi importati restano tutti da confermare. Le nuove statistiche mantengono esplicitamente le ore mancanti, coerentemente con questa caratteristica della fonte.

## Librerie e licenze

| Risorsa | Uso effettivo | Licenza |
|---|---|---|
| **XlsxWriter 3.2.9**, aggiunta nella 0.8 | Generazione .xlsx senza Excel sul server | BSD-2-Clause, inclusa |
| CSS/JavaScript nativi | Grafici, filtri, download e stili | Codice del progetto |
| Roboto locale | Tipografia | OFL-1.1 |
| Lucide Static 0.468.0 | Icone, riusate anche nelle nuove pagine | ISC, attribuzione Feather MIT |
| Waitress 3.0.2 | Servizio WSGI | ZPL-2.1 |
| PyOTP 2.9.0 | TOTP | MIT |
| Segno 1.6.6 | QR locali | BSD-3-Clause |
| cryptography 50.0.2 | Segreti TOTP cifrati | Apache-2.0 oppure BSD-3-Clause |

Per XlsxWriter verificate la licenza inclusa nella versione effettivamente distribuita e le fonti ufficiali: https://xlsxwriter.readthedocs.io/license.html e https://pypi.org/project/XlsxWriter/3.2.9/ . Le opzioni per le stringhe non eseguibili come formule e i tipi di celle sono documentate in https://xlsxwriter.readthedocs.io/workbook.html . La nuova libreria è gratuita anche per l'utilizzo commerciale secondo la licenza, con gli obblighi di attribuzione conservati. Non sono richiesti abbonamenti o funzionalità a pagamento per gli export.

Le altre risorse e le loro attribuzioni erano già conservate nel progetto. Nessuna nuova libreria grafica pesante aggiunta. Georgia è un font di sistema, senza file distribuiti. Il logo NefroCenter rimane una risorsa del gruppo, non open source. Non è stato acquistato o attivato alcun servizio.

## Limiti residui

- Portale ancora da installare e collaudare sull'infrastruttura reale: HTTPS/certificato, rete tra sedi, Windows, telefono fisico per QR, browser diversi, carico concorrente e riavvio/restore aziendale.
- Backup automatici locali al server; nessuna copia remota automatica né politica di cancellazione implementate. La chiave originale 2FA va conservata separatamente. Backup oltre 256 MiB si prelevano amministrativamente dal server.
- Database HR e allegati non cifrati integralmente dall'app; la cifratura applicativa riguarda i segreti TOTP. Nessuna modalità offline o alta disponibilità dimensionata.
- Ruoli storici non disponibili: statistiche per ruolo attuale. Anagrafiche per centro, non persone globali deduplicate. I conteggi di fasce non equivalgono a giornate contrattuali.
- Gli export sono copie dei risultati, senza formule ricalcolabili o importazione bidirezionale. Nessuna apertura in Microsoft Excel desktop è stata effettuata in questo ambiente; struttura e valori sono verificati come OOXML e i file scaricati nel browser.
- Accordi e calcoli non sostituiscono paghe, contributi o netto in busta. Le impostazioni individuali e i calendari richiedono validazione aziendale.
- Nessun audit indipendente di sicurezza o accessibilità; verifiche puntuali descritte sopra.

## Contenuto e integrità della consegna unica

Codice completo 0.8, dipendenze incluse/licenze, guide, contesto utente, documento di passaggio a Codex, test e risultati, anteprima storica, analisi del modello e rollback 0.7/0.6. `SHA256SUMS.txt` permette il controllo delle impronte. Nessun database operativo, foglio Excel originale, dato dipendente reale, chiave di produzione o credenziale aziendale è incluso.
