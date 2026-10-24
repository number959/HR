# Edizione qualità 0.11.1 — 23 ottobre 2026

Questo aggiornamento migliora guide e materiali di presentazione della versione funzionale 0.11. Il database resta allo schema 8 e `/health` continua a indicare 0.11. Non modifica i dati aziendali o abilita invii email e promemoria.

## Cosa cambia

- Guida nel portale riscritta per 34 procedure: prerequisiti, passaggi, risultato atteso, esempio pratico, problemi frequenti e schermate ingrandibili.
- Sette percorsi guidati per iniziare o seguire il lavoro di compilatore, responsabile, HR, amministratore e direzione; ricerca nelle 323 impostazioni.
- 34 videoguide illustrate Full HD 1920×1080 a 30 fps, senza audio, con copertine, capitoli, sottotitoli leggibili e trascrizioni. Mostrano schermate di riferimento e istruzioni, non una registrazione interattiva delle operazioni.
- Manuale illustrato PDF/HTML e presentazione dedicata all’ufficio HR, con indice, esempi e schermate reali della demo.
- Presentazione generale aggiornata alla 0.11: 2 minuti e 37 secondi, Full HD a 30 fps, disponibile con voce sintetica italiana oppure senza audio. Il player della demo permette di scegliere fra 11 capitoli.
- Corretto l’adattatore della demo: solo l’amministratore può configurare le soglie delle approvazioni, come nel gestionale operativo.

## Consultazione

La demo resta **https://nefrocenter-demo.icy-bass-2671.chatgpt.site**. Dalla pagina iniziale apri la presentazione o il PDF HR; nel gestionale apri **Guide e tutorial**, scegli un percorso o cerca una parola. Il pulsante **Manuale illustrato · PDF** apre il manuale completo. I file consegnati si possono consultare anche offline.

Per i campi e le impostazioni usa la ricerca della Guida o `Riferimento_Impostazioni_NefroCenter_v0.11.html`. Le indicazioni dei ruoli descrivono i permessi del software: selezionare un percorso nella Guida non cambia i permessi dell’account.

## Aggiornamento e sorgenti

Per installare o aggiornare usa `INSTALLAZIONE_IN_BREVE.md`, `INSTALLAZIONE_WEB.md` e `AGGIORNAMENTO_0.11.md`. Prima di sostituire il codice conserva il backup di database, allegati, chiavi e configurazione indicato da quelle istruzioni. Le funzioni SMTP, NAS e paghe richiedono ancora configurazione aziendale.

Il pacchetto conserva i sorgenti delle guide in `docs/help_quality.json`, il generatore `qa/generate_guides.py`, il renderer `qa/render_guide_videos.py`, le schermate sintetiche in `assets/guide_screens/` e i sorgenti della presentazione in `qa/presentation_quality/`. Gli strumenti per generare media richiedono dipendenze aggiuntive documentate nelle rispettive guide; non servono per utilizzare il portale.

Gli esiti effettivi dei controlli e della pubblicazione sono in `VERIFICA.md` e `STATO_PROGETTO.json`.
