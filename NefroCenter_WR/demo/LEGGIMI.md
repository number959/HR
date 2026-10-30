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
python costruisci_demo.py                    # versione leggera (2,8 MB): Pyodide dalla rete pubblica jsDelivr
python costruisci_demo.py --includi-pyodide  # versione autonoma (17,8 MB): funziona anche senza Internet
python costruisci_demo.py --includi-pyodide --solo-file-web --cartella ALTRA_CARTELLA
                                             # variante per servizi che pubblicano solo tipi di file web (vedi sotto)
```

Il risultato è la cartella `dist/` (si può ricreare in ogni momento). Contiene l'interfaccia del portale,
il motore (`motore.zip`), l'archivio fittizio (`dati/wr.sqlite3`), `versione.json` e, con `--includi-pyodide`,
la cartella `pyodide/`. Manuale illustrato e videoguide (`gestionale/web/help`) restano fuori per tenere la demo
leggera: la guida in linea del portale c'è comunque.

## Provarla sul proprio computer

```bash
python avvia_demo.py                  # apre il browser su http://127.0.0.1:8000/
python avvia_demo.py --lan            # anche dagli altri computer della stessa rete (stampa l'indirizzo)
python avvia_demo.py --senza-browser  # senza aprire il browser da solo; --port 8001 per un'altra porta
```

Non basta aprire `index.html` con un doppio clic: la demo va servita via HTTP, e ci pensa `avvia_demo.py`.

**Pacchetto pronto all'uso.** `strumenti/consegna.py` produce `NefroCenter_WR_Demo_1.0.0.zip`: la cartella `dist/`
(con Pyodide, se costruita così) più `avvia_demo.py` e i lanciatori della cartella `lancio/`: `Avvia_demo.bat`
(Windows, doppio clic), `avvia_demo.command` (macOS, doppio clic; la prima volta tasto destro → Apri),
`avvia_demo.sh` (Linux) e `LEGGIMI_DEMO.txt`. Serve solo Python 3 installato.

## Pubblicarla

La demo **non è pubblicata su un indirizzo dell'azienda**. La demo della versione precedente (0.11) è ancora
all'indirizzo indicato nella documentazione della 0.11. Decidere se la demo WR la sostituisce o la affianca spetta
all'azienda; poi basta copiare la cartella `dist/` su un servizio di siti statici con HTTPS. La demo funziona anche
servita da una sottocartella (per esempio `https://sito/demo-wr/`).

Il 30 ottobre 2026 una copia della demo è stata caricata come **pagina privata di prova** su claude.ai, visibile
solo al titolare del progetto finché non la condivide: è un'anteprima per valutare la demo, non la pubblicazione
ufficiale. Quel servizio pubblica soltanto tipi di file web, perciò la copia è costruita con `--solo-file-web`:
archivi e database diventano file di testo base64 (`versione.json` li elenca in `file_base64`) che `demo-main.js`
decodifica nel browser prima di consegnarli a Pyodide. Lo stesso caricatore, dentro un visualizzatore che blocca gli
scaricamenti diretti, consegna CSV ed Excel attraverso il servizio di salvataggio del visualizzatore
(`setDownloader` in `api.js`); nel portale aziendale e nella demo servita da un sito statico non cambia nulla.

## Verifica automatica

Con Node.js e Playwright: avviare `python avvia_demo.py --port 8095`, poi
`node prova_demo.cjs CARTELLA_SCHERMATE http://127.0.0.1:8095`. La prova avvia il motore, entra come
responsabile, apre tutte le pagine del suo menu, registra una presenza e scarica un CSV.
