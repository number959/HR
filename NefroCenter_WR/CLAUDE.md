# NefroCenter WR · Work Resources — istruzioni per chi riprende il lavoro

Leggi `PASSAGGIO_PROGETTO.md` (contesto, decisioni, mappa dei sorgenti), poi `gestionale/VERIFICA.md` e `gestionale/STATO_PROGETTO.json`.

Regole fisse:

- Distingui sempre la **demo pubblica** (dati fittizi, profili senza password, email simulate, vive nel browser) dal **portale aziendale** (account personali, dati reali, servizi da configurare).
- NAS, servizio di posta e tracciato paghe **non sono configurati**: non inventare parametri, non attivare invii reali, non presumere destinazioni.
- Non eseguire mai `manage.py init` su un archivio esistente; `after-restore` non è in sola lettura. La migrazione dalla 0.11 lavora su una copia e non tocca l'archivio di origine.
- Solo dati fittizi in sorgenti, prove, schermate, video e demo. Nessuna chiave, password, archivio aziendale, allegato o file Excel reale nel repository.
- Non pubblicare la demo né creare siti duplicati senza una richiesta esplicita; non spingere su repository pubblici senza consenso.
- Italiano semplice nell'interfaccia, nei documenti e nei messaggi; nomi inglesi e commenti italiani nel codice. Nessuno stile o script in linea nell'interfaccia (CSP severa).
- Dopo ogni modifica: prove automatiche (`cd gestionale && python3 -m unittest discover -s tests -p "test_*.py"`), giro dell'interfaccia (`node strumenti/giro_interfaccia.cjs`), e rigenerazione di manuale e videoguide se cambiano le pagine documentate.
- Riporta sempre cosa hai modificato, quali controlli hai davvero eseguito e cosa resta da completare.
