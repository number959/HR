# Rigenerare i manuali illustrati

Questi strumenti generano il manuale operativo illustrato, la presentazione per HR e il riferimento HTML delle 323 impostazioni. I testi provengono da `docs/help_catalog.json`, aggiornati con `docs/help_quality.json`; le immagini da `assets/guide_screens/manifest.json` e dai relativi WebP. Le schermate sono dimostrative. Non vengono interrogati archivi aziendali.

## Requisiti

- Python 3 con Pillow; pypdf per il controllo dei PDF.
- Node.js con Playwright e un browser Chromium locale.
- I tre script presenti in `qa/`: `build_manual.py`, `render_manual.cjs`, `verify_manual_pdf.py`.

## Esecuzione da terminale

Dalla cartella principale del software, in un ambiente con le dipendenze già installate:

```sh
export NEFRO_APP_ROOT="$PWD"
export NEFRO_MANUAL_WORK="$PWD/qa/manual-work"
export NEFRO_MANUAL_OUT="$PWD/docs/manuali"
mkdir -p "$NEFRO_MANUAL_WORK" "$NEFRO_MANUAL_OUT"
python qa/build_manual.py --require-images
node qa/render_manual.cjs
python qa/verify_manual_pdf.py
```

Senza altre impostazioni viene usato il Chromium installato con Playwright. Per un browser diverso indicare `CHROMIUM_EXECUTABLE` (è accettato anche il nome storico `NEFRO_CHROMIUM`). Solo in un contenitore di collaudo isolato che non supporta la sandbox aggiungere `QA_CHROMIUM_NO_SANDBOX=1`. Se `NEFRO_MANUAL_OUT` non è impostata, i file vengono scritti in `docs/manuali` della cartella corrente. Su Windows impostare le stesse variabili con la sintassi PowerShell `$env:NOME = 'percorso'`.

Il browser legge gli HTML attraverso un server temporaneo su `127.0.0.1`, chiuso al termine. Le immagini sono incorporate negli HTML: i documenti risultanti si consultano senza caricare risorse esterne. I link espliciti alla demo pubblica richiedono una connessione.

## Risultati

- `Guida_NefroCenter_v0.11_illustrata.pdf` e `.html`: 34 schede operative, percorsi per ruolo e indice cliccabile, 42 pagine PDF nell’edizione corrente.
- `Presentazione_HR_NefroCenter_v0.11_illustrata.pdf` e `.html`: 11 pagine per la riunione, con esempi e una scaletta di dieci minuti.
- `Riferimento_Impostazioni_NefroCenter_v0.11.html`: 323 riferimenti ricercabili e filtrabili per pagina, stampabili anche dopo una ricerca.

Il renderer salva l’HTML con le stesse classi di stampa usate per il PDF. Non modificare a mano il PDF: aggiornare il catalogo o lo script e rigenerare entrambi.

## Controlli

Il renderer controlla altezza delle pagine, navigazione dell’indice, assenza di errori JavaScript, ricerca e filtro del riferimento, e larghezza mobile a 390 pixel. Il verificatore controlla numero di pagine, pagine quasi vuote, segnalibri, struttura PDF con tag e assenza di link temporanei localhost.

I rapporti `manual-validation.json`, `manual-fit.json` e `manual-pdf-validation.json` sono nella cartella di lavoro. Le immagini `qa-*.png` permettono il controllo visivo. Cambiamenti editoriali estesi possono richiedere di aggiornare i conteggi attesi nel verificatore dopo aver controllato l’impaginazione.
