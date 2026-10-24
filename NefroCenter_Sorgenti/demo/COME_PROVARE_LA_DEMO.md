# Provare e condividere la demo 0.11 · edizione qualità 0.11.1

Questa è una demo statica con 3 centri, 12 anagrafiche fittizie e 5 profili selezionabili senza password. Ogni visitatore usa una propria copia: le modifiche restano nella scheda del browser e non si condividono con gli altri. Non inserire dati reali.

## Sul tuo computer

Installa Python 3.12 o superiore, estrai tutto lo ZIP e apri un terminale nella cartella della demo:

```bash
python avvia_demo.py
```

Apri **http://localhost:8000**. Non basta aprire index.html con un doppio clic: la demo deve essere servita via HTTP.

## Farla provare ad altri sulla stessa rete

```bash
python avvia_demo.py --lan
```

Le altre persone aprono `http://IP_DEL_TUO_PC:8000`; per esempio, se il PC ha indirizzo 192.168.1.20, aprono `http://192.168.1.20:8000`. Il PC deve restare acceso e il firewall deve consentire questa connessione sulla rete aziendale. Chiedi al tecnico di verificare l’indirizzo e la raggiungibilità. Questo comando serve solo i contenuti di `dist/`, con dati dimostrativi.

## Link Internet

La demo è online: **https://nefrocenter-demo.icy-bass-2671.chatgpt.site**.

Condividi questo indirizzo con le persone che vuoi far partecipare: non servono account o password. Chiunque abbia il link può aprire la demo e scegliere uno dei cinque profili. Non caricare dati aziendali: tutti i dati iniziali sono pubblici e fittizi, le modifiche rimangono nella sessione di ciascun visitatore.

La cartella `dist/` può anche essere pubblicata da un tecnico su un proprio hosting statico HTTPS.

## Cosa provare

La pagina iniziale spiega cosa fa il software e presenta ogni ruolo con ambito, funzioni, limiti ed esempio pratico. Per la riunione HR, scarica **Guida per l’ufficio HR · PDF**, guarda la presentazione e inizia da **HR centrale**. La guida comprende la panoramica dei moduli, i flussi di lavoro e una scaletta per la dimostrazione.

- Scegli Compilatore, inserisci una presenza e controlla i totali.
- Scegli Responsabile o Amministratore e consulta un fascicolo con onboarding.
- In Documenti usa **Allega documento dimostrativo**; poi **Cambia profilo → HR centrale** per vedere l’allegato nella stessa sessione.
- Come HR centrale o Amministratore, apri **Strutture**, modifica un recapito fittizio e ritrovalo nella sezione **Struttura di riferimento** del fascicolo.
- In **Comunicazioni**, scegli un modello e una lista, genera l’anteprima, controlla destinatari e messaggi e crea una bozza. **Simula invio** chiede una conferma e aggiorna soltanto lo storico dimostrativo: non parte alcuna email. Prova anche una lista indirizzata ai contatti HR delle strutture.
- Esplora le 34 guide per pagina, le 323 impostazioni spiegate e le 34 videoguide illustrate Full HD con sottotitoli e trascrizioni. Le videoguide delle pagine sono senza audio.
- Apri **Guarda la presentazione** dalla pagina iniziale, oppure dal pannello informativo **ⓘ**: la presentazione del prodotto comprende una versione con voce sintetica italiana e una senza audio, scaricabili separatamente.
- Usa **Ripristina demo** per tornare al campione iniziale.

Statistiche e CSV del registro si aggiornano durante la prova. Excel, identità, decorrenze e accordi mostrano il campione iniziale dichiarato nell’interfaccia. NAS, account veri, 2FA, importazioni e servizio SMTP si configurano nell’installazione completa. I recapiti della demo sono fittizi e non vengono contattati. Il caricamento di file personali è sostituito dal PDF fittizio.

Le API dimostrative 0.11 sono state controllate offline per tutti e cinque i profili. Il percorso browser comprende tutte le pagine accessibili a 1400 e 390 px, documenti PDF, video e simulazione email. Il rapporto `VERIFICA.md` della consegna del gestionale registra l’esito finale e gli eventuali controlli ancora da completare.

Per ripetere il collaudo browser in una copia di sviluppo: installare Node.js, Playwright e Chromium, avviare `python avvia_demo.py --port 8765` e, in un altro terminale, eseguire `node demo-browser-check.cjs`. Sono strumenti di sviluppo: per usare la demo basta il browser. Il percorso di Chromium è configurabile con `CHROMIUM_EXECUTABLE`; impostare `QA_CHROMIUM_NO_SANDBOX=1` soltanto nei contenitori isolati che lo richiedono.

## Nuovi percorsi della 0.11

- In **Approvazione mese** segui invio sede, verifica responsabile e approvazione HR; restituisci con nota per riaprire la compilazione. Usa un mese con consuntivi completi per arrivare alla chiusura.
- In **Documenti HR** apri Verifica: HR richiede correzioni o conferma; il responsabile può ripresentare il documento corretto. Lo storico resta nella sessione dimostrativa.
- In **Copertura turni** configura i minimi come amministratore o responsabile, registra disponibilità e consulta le scoperture. Le sostituzioni richiedono anagrafiche collegate; la sede destinataria decide.
- In **Promemoria** consulta l’anteprima. L’amministratore può simulare la configurazione: nessuna email parte e nessun programma continua a girare dopo aver chiuso la pagina.
- In **Paghe** importa solo le intestazioni o una specifica JSON di esempio e controlla la mappatura; il fornitore reale resta da indicare.
- In **Uscite e dotazioni** registra consegna/restituzione e completa la checklist prima di chiudere il percorso.

Le approvazioni sono attive nelle sedi dimostrative, mentre nel software installabile richiedono attivazione. Cambia ruolo nella stessa scheda per seguire i passaggi tra uffici. Ogni visitatore ha una copia separata: le persone invitate alla demo non modificano l’una i dati dell’altra. La presentazione generale aggiornata dura 2 minuti e 37 secondi, con 11 capitoli selezionabili. La Guida offre sette percorsi per ruolo, prerequisiti, esempi, problemi frequenti e un manuale PDF illustrato.

Il launcher locale incluso supporta i salti ai capitoli dei video anche prima della riproduzione. Usa `avvia_demo.py` per conservare questo comportamento nella copia scaricata.
