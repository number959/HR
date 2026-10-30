# NefroCenter WR · Work Resources 1.0

Il portale del personale delle strutture NefroCenter: presenze e turni, persone e fascicoli, documenti, approvazioni, accordi, paghe, comunicazioni, statistiche. È la riscrittura completa di «Persone e Presenze Web 0.11», con lo stesso perimetro di funzioni, un nuovo motore e una nuova interfaccia.

## Le cartelle

| Cartella | Contenuto |
|---|---|
| `gestionale/` | l'applicazione: `manage.py` (console), `wr/` (motore Python), `web/` (interfaccia), `vendor/` (librerie incluse), `tests/` (154 prove automatiche), `deploy/` (esempi di servizio), `strumenti/anteprima.py` (portale di prova con dati fittizi) |
| `gestionale/web/help/` | manuale illustrato e videoguide generati dalle schermate del portale (dati fittizi) |
| `demo/` | demo pubblica: lo stesso motore eseguito nel browser (Pyodide) con dati fittizi; `costruisci_demo.py` crea `dist/`, `avvia_demo.py` e `lancio/` la avviano con un doppio clic |
| `strumenti/` | prove dell'interfaccia (Playwright), generatori di manuale e videoguide, archivio 0.11 di prova, `consegna.py` per ZIP e TXT |

## Da dove partire

- **Installare il portale in azienda**: `gestionale/INSTALLAZIONE_PASSO_PASSO.md` (guida dettagliata, anche per provarlo subito) e `gestionale/INSTALLAZIONE.md` (riferimento tecnico).
- **Portare i dati della 0.11**: `gestionale/MIGRAZIONE_DALLA_0.11.md`.
- **Cosa è cambiato**: `gestionale/NOVITA_WR_1.0.md`.
- **Controlli eseguiti e limiti**: `gestionale/VERIFICA.md`, `gestionale/STATO_PROGETTO.json`.
- **Provare la demo sul proprio PC**: `demo/LEGGIMI.md`.
- **Continuare lo sviluppo**: `PASSAGGIO_PROGETTO.md` (e `CLAUDE.md` per gli assistenti di programmazione).
- **Ricreare i sorgenti dal file TXT**: `SORGENTE_IN_TXT.md`.

## Due cose da non confondere

La **demo pubblica** ha dati inventati, profili senza password, email simulate e vive nella scheda del browser di chi prova. Il **portale aziendale** ha account personali con password e app Authenticator, dati reali sul server, backup, e servizi (posta, NAS, paghe) da configurare con il tecnico: finché non sono configurati restano spenti.

Nessun file di questo progetto contiene dati aziendali, password o chiavi.
