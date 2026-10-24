# Verifica NefroCenter 0.10 — 21 ottobre 2026

## Stato del collaudo

**182 test Python superati**, in 152,645 secondi. La suite finale comprende strutture, comunicazioni, recupero dei lotti interrotti, ripristino e regressioni precedenti. Log: `qa/unit-tests.log`.

**Collaudo Chromium del gestionale 0.10 superato** contro Waitress e un database temporaneo: accessi e 2FA, permessi, rubrica e fascicolo, liste email, anteprima e bozze con SMTP disattivato, guide, quattro stili e verifiche mobile a 390/320 px, oltre alle regressioni delle versioni precedenti. Log: `qa/browser-tests.log`.

**Demo 0.10 verificata con API e Chromium per tutti e cinque i ruoli:** 19 pagine per amministratore, 17 per HR, 17 per responsabile, 10 per compilatore e 10 per lettore, a 1400 e 390 px. Verificati strutture, simulazione delle comunicazioni, documenti e video. Log: `qa/demo-api-check.log` e `qa/demo-browser-tests.log`. Il player della presentazione ha superato anche il controllo dedicato: riproduzione di 88 secondi, sottotitoli VTT, download delle due versioni, accesso dalla pagina iniziale e dal pannello ⓘ di HR, pausa alla chiusura e larghezze 1400/390/320 px. Log: `qa/demo-presentation-tests.log`.

**Presentazione HR e scelta del ruolo:** cinque schede con scopo, ambito, operazioni, limiti ed esempi; ingresso e cambio profilo verificati a 1400/768/390/320 px. PDF di sette pagine generato e controllato, download dalla demo verificato. Log: `qa/demo-roles-tests.log`.

## Funzioni verificate

- **Strutture:** dati comuni collegati ai fascicoli, autorizzazioni aggiornate a ogni operazione, visibilità dei centri assegnati, validazione dei recapiti e URL, versioni concorrenti e storico. Le modifiche della rubrica sono visibili nei fascicoli senza copie separate.
- **Comunicazioni:** accesso riservato ad amministratori e HR centrale; configurazione SMTP solo amministratore; modelli e variabili ammesse; filtri delle liste, esclusioni, deduplicazione e anomalie; controllo delle anteprime obsolete; destinatari e testi conservati nella bozza.
- **Invio simulato nei test:** destinatario individuale, TLS obbligatorio, credenziali esterne al database, limite del lotto e del numero di tentativi orari. Conferme legate al lotto corrente impediscono richieste concorrenti o ripetute di spedire un lotto successivo non confermato. Errori prima dell'accettazione SMTP ed esiti incerti seguono percorsi distinti; gli incerti non vengono reinviati automaticamente.
- **Interruzione e ripristino:** un lotto abbandonato può essere classificato esplicitamente come incerto dopo 15 minuti, senza inviare email. `manage.py after-restore` disabilita SMTP e sospende gli invii pendenti o in lavorazione, oltre alla revoca di sessioni e codici di recupero.
- **API HTTP:** isolamento dei centri, lettura protetta, secondo fattore recente per invio/configurazione, configurazione oscurata a HR e pubblicazione delle sole risorse ammesse.
- **Percorso browser 0.10:** salvataggio dei recapiti della struttura e lettura nel fascicolo; aiuto contestuale; lista di dipendenti, anteprima personalizzata, segnalazione indirizzi mancanti, creazione della bozza e invio disattivato. Nuove pagine e modali controllate a 390 e 320 px.
- **Guide:** 30 argomenti, 225 impostazioni e 30 videoguide illustrate senza audio, con sottotitoli e trascrizioni. Le due nuove videoguide Strutture e Comunicazioni sono state lette con ffprobe e ispezionate visivamente. La presentazione del prodotto è un contenuto multimediale separato: 88 secondi, Full HD H.264, in versione senza audio e con voce sintetica italiana ElsaNeural e traccia AAC mono a 48 kHz. Sono disponibili sottotitoli e trascrizioni.

Nessuna email reale è stata spedita: i test sostituiscono il trasporto SMTP e la demo simula l'invio nella sessione del visitatore. **Accettato da SMTP non significa consegnato o letto.**

## Funzioni precedenti conservate

La suite comprende anche autenticazione e recupero 2FA, permessi HR centrale, documenti protetti delle sedi, presenze, statistiche, sei prospetti Excel, migrazione, accordi, attività, identità collegate, decorrenze e modelli paghe. Le copie NAS sono provate su cartelle temporanee; nessun NAS aziendale reale è stato collegato. Non è stato fornito né certificato il tracciato paghe del consulente.

Il collaudo browser precedente controlla quattro stili e più larghezze, documenti, esportazioni, backup, aiuto e tutorial, usando Waitress e un archivio temporaneo con dati fittizi. Il collaudo demo 0.10 ha coperto cinque profili su tutte le pagine accessibili e il player della presentazione è stato verificato separatamente.

## Pubblicazione e verifiche sull'ambiente aziendale

La demo 0.10 è pubblicata: https://nefrocenter-demo.icy-bass-2671.chatgpt.site. Pubblicazione della versione del sito 4 confermata dal servizio di hosting. Usa dati fittizi e modifiche separate per scheda. Il gestionale operativo non è installato sul server aziendale.

Nel sistema definitivo restano da verificare HTTPS e accessi dalle sedi, server e riavvio del servizio, NAS e relativo montaggio/permessi, ripristino completo con chiave 2FA originale, tracciato paghe del consulente e compatibilità del servizio di posta. Il fornitore SMTP non è ancora stato scelto; la configurazione iniziale lascia gli invii disattivati. Il collaudo locale con trasporto simulato non verifica consegna reale, limiti del fornitore, OAuth/API proprietarie o reputazione del dominio mittente.

## Riprodurre le prove

```bash
python -m unittest discover -v
python -m unittest test_structures test_communications test_web_v010 -v
CHROMIUM_EXECUTABLE=/usr/bin/chromium QA_CHROMIUM_NO_SANDBOX=1 python qa/run_browser.py
```

Il comando browser richiede Node.js, Playwright, Chromium e loopback. Usare `QA_CHROMIUM_NO_SANDBOX=1` solo quando il contenitore isolato di collaudo lo richiede. Il percorso crea un archivio temporaneo con dati fittizi: non eseguirlo contro un archivio aziendale. I test mirati sono facoltativi quando la suite completa appena eseguita ha già verificato le stesse modifiche.

Ambiente: Python 3.12.14, cryptography 50.0.2, Node.js 24.19.0, Playwright 1.62.1 e Chromium 154.0.8037.57. I log finali della consegna sono conservati in `qa/unit-tests.log`, `qa/browser-tests.log`, `qa/demo-api-check.log` e `qa/demo-browser-tests.log` e `qa/demo-presentation-tests.log`; gli esiti storici rimangono separati in `qa/history/`.
