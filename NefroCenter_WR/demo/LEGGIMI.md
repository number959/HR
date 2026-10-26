# NefroCenter WR · demo pubblica

La demo serve a far provare il portale senza installarlo. **Non è il portale aziendale.**

| | Demo pubblica | Portale aziendale |
|---|---|---|
| Dati | Solo fittizi (3 strutture, 12 persone, ottobre 2026) | Dati reali dell'azienda |
| Accesso | 5 profili da scegliere, senza password | Account personale, password e app Authenticator |
| Dove girano i dati | Nella scheda del browser di chi prova | Sul server aziendale |
| Modifiche | Restano solo in quella scheda e spariscono alla chiusura | Salvate nell'archivio, con backup |
| Email | Sempre simulate: non parte nulla | Solo dopo la configurazione della posta aziendale |
| NAS, paghe, promemoria | Non configurabili | Da configurare con i dati reali |

Il motore è **lo stesso** del portale aziendale (stesso codice Python): nel browser lo esegue Pyodide.
Così la demo mostra esattamente le regole, i controlli e le pagine del portale vero.

## Costruire la demo

Dalla cartella `demo`:

```bash
python costruisci_demo.py                    # versione leggera (2,6 MB): Pyodide dalla rete pubblica jsDelivr
python costruisci_demo.py --includi-pyodide  # versione autonoma (circa 18 MB): funziona anche senza quella rete
```

Il risultato è la cartella `dist/` (si può ricreare in ogni momento). Contiene l'interfaccia del portale,
il motore (`motore.zip`), l'archivio fittizio (`dati/wr.sqlite3`) e `versione.json`.

## Provarla sul proprio computer

```bash
python avvia_demo.py          # poi aprire http://localhost:8000
python avvia_demo.py --lan    # anche dagli altri computer della stessa rete
```

Non basta aprire `index.html` con un doppio clic: la demo va servita via HTTP.

## Pubblicarla

La demo **non è pubblicata**. La demo della versione precedente (0.11) è ancora all'indirizzo indicato nella
documentazione della 0.11. Decidere se la demo WR la sostituisce o la affianca spetta all'azienda; poi basta
copiare la cartella `dist/` su un servizio di siti statici con HTTPS.

## Verifica automatica

Con Node.js e Playwright: avviare `python avvia_demo.py --port 8095`, poi
`node prova_demo.cjs CARTELLA_SCHERMATE http://127.0.0.1:8095`. La prova avvia il motore, entra come
responsabile, apre tutte le pagine del suo menu, registra una presenza e scarica un CSV.
