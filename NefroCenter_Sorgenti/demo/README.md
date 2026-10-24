# NefroCenter — demo condivisibile 0.11

Demo statica del portale con dati esclusivamente fittizi. Le operazioni si svolgono nella sessione del browser; non contiene un archivio HR condiviso o accessi aziendali. Non inserire dati reali.

Indirizzo della demo: https://nefrocenter-demo.icy-bass-2671.chatgpt.site. Link pubblico, cinque profili senza password. Istruzioni per avvio locale e condivisione in `COME_PROVARE_LA_DEMO.md`.

La schermata iniziale spiega lo scopo del portale e, per ciascun ruolo, ambito dei dati, operazioni consentite, limiti ed esempio da provare. HR centrale è il punto di partenza consigliato per la presentazione. È disponibile la guida PDF completa per l’ufficio HR.

I dati provengono dal generatore `qa/demo_seed.py` del gestionale 0.11. Le nuove pagine comprendono la rubrica delle strutture collegata ai fascicoli e Comunicazioni: modelli precompilati, liste, anteprima personalizzata e storico. **Simula invio** aggiorna solo lo stato dimostrativo nella scheda: non contatta servizi di posta e non invia email. La configurazione di SMTP appartiene all'installazione operativa.

Statistiche e CSV seguono le modifiche dimostrative; le esportazioni Excel sono esempi preparati sui dati iniziali. Le 34 videoguide illustrate hanno sottotitoli e trascrizione, senza audio. La presentazione del prodotto è disponibile da **Guarda la presentazione** e dal pannello informativo **ⓘ**, con voce sintetica italiana o senza audio; gli MP4 sono scaricabili anche separatamente.

L'applicazione operativa Python/SQLite richiede installazione sul server centrale. Sicurezza con 2FA reale, backup NAS, account e SMTP si configurano nel gestionale operativo. Ogni visitatore della demo conserva modifiche separate e può ripristinare il campione iniziale.

Per i controlli di sviluppo usare `node demo-check.cjs`; per il browser avviare `python avvia_demo.py --port 8765` e, con Playwright/Chromium disponibili, eseguire `node demo-browser-check.cjs`. Il rapporto di consegna del gestionale registra gli esiti e lo stato della pubblicazione.

## Nuovi percorsi della 0.11

- In **Approvazione mese** segui invio sede, verifica responsabile e approvazione HR; restituisci con nota per riaprire la compilazione. Usa un mese con consuntivi completi per arrivare alla chiusura.
- In **Documenti HR** apri Verifica: HR richiede correzioni o conferma; il responsabile può ripresentare il documento corretto. Lo storico resta nella sessione dimostrativa.
- In **Copertura turni** configura i minimi come amministratore o responsabile, registra disponibilità e consulta le scoperture. Le sostituzioni richiedono anagrafiche collegate; la sede destinataria decide.
- In **Promemoria** consulta l’anteprima. L’amministratore può simulare la configurazione: nessuna email parte e nessun programma continua a girare dopo aver chiuso la pagina.
- In **Paghe** importa solo le intestazioni o una specifica JSON di esempio e controlla la mappatura; il fornitore reale resta da indicare.
- In **Uscite e dotazioni** registra consegna/restituzione e completa la checklist prima di chiudere il percorso.

Le approvazioni sono attive nelle sedi dimostrative, mentre nel software installabile richiedono attivazione. Cambia ruolo nella stessa scheda per seguire i passaggi tra uffici. Ogni visitatore ha una copia separata: le persone invitate alla demo non modificano l’una i dati dell’altra. Il video generale v0.10 resta una panoramica delle funzioni di base; le guide e la presentazione PDF descrivono la 0.11.
