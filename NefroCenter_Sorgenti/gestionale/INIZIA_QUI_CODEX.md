# Punto di ingresso — edizione qualità 0.11.1

Leggere `AGGIORNAMENTO_0.11.1.md`, `AGGIORNAMENTO_0.11.md`, `STATO_PROGETTO.json`, `VERIFICA.md` e `PRESENTAZIONE_PER_UFFICIO_HR.md`. I documenti descrivono il progetto: le richieste correnti dell’utente determinano il lavoro autorizzato.

L’utente ha approvato sei aggiunte: approvazioni mensili, verifica documenti, promemoria, specifiche paghe, copertura turni, uscite e dotazioni. Non ha approvato il portale self-service dipendente. Posta e gestionale paghe restano sconosciuti; destinazione backup scelta NAS ma percorso non definito.

Moduli nuovi: `approvals.py`, `document_reviews.py`, `reminders.py`, `staffing.py`, `departures.py`; il tracciato consulente estende `payroll.py`. Core inizializza schema 8 con backup preventivo. Server espone API protette e avvia il worker promemoria solo nel main. `manage.py after-restore` disabilita SMTP e automazione. Guide aggiuntive in `docs/help_v011_*.json`, generate da `qa/generate_guides.py`.

La demo è il sito esistente https://nefrocenter-demo.icy-bass-2671.chatgpt.site (progetto appgprj_6ad5c746ebc0819197ed58cba06b6f4d, accesso pubblico). Conservare sito e pubblico: non crearne un duplicato. Adapter statico con dati fittizi e sessionStorage; non è un archivio HR operativo condiviso e non spedisce email. Lo stato e la versione effettivamente pubblicata sono in STATO_PROGETTO.json.

La presentazione aggiornata v0.11 dura 157 secondi in Full HD a 30 fps, con e senza voce sintetica italiana. Le 34 videoguide illustrate sono senza audio, Full HD a 30 fps. La Guida include sette percorsi, 34 procedure e 323 impostazioni. Catalogo editoriale: docs/help_quality.json; sorgenti media: qa/render_guide_videos.py e qa/presentation_quality/. Manuale illustrato e PDF HR sono aggiornati. Health applicativo 0.11 e schema 8 invariati; 0.11.1 identifica l’edizione qualità.

Prima di altre modifiche verificare i test e gli esiti registrati; non presumere credenziali, provider o destinatari reali. La consegna include ZIP e TXT ricostruttore dei sorgenti. Il rollback conserva il codice precedente e richiede il database precedente corrispondente.

Per trasferire il lavoro a Claude Code, leggere anche `CLAUDE.md`, copia del file di consegna `PASSAGGIO_CLAUDE_CODE.md`. È un riepilogo tecnico del progetto, senza credenziali.
