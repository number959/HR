# Verifica — NefroCenter WR · Work Resources 1.0.0

Controlli eseguiti tra il 25 e il 29 ottobre 2026 in un contenitore Linux (Python 3.13, Node 22, Playwright 1.63 con Chromium), sempre con dati fittizi. Il collaudo sul server aziendale e sulla rete reale **non** è stato eseguito.

## Motore (prove automatiche)

`python3 -m unittest discover -s tests -p "test_*.py"`: **154 prove**, tutte superate (circa 35 secondi). Coprono archivio e schema, accessi (password, app Authenticator, codici di recupero, conferma di sicurezza), registro e regole, controlli del mese e chiusura, approvazioni, accordi e calcoli (compresa la correzione del teorico), fascicoli e documenti, personale di gruppo, copertura e sostituzioni, uscite, paghe, statistiche ed esportazioni, comunicazioni, backup e seconda copia, migrazione dalla 0.11 (13 prove), importazione Excel (13 prove, con file sintetici che riproducono il modello reale e file ostili), prospetto collaboratori (3 prove), indicatori di carico e conteggi (prove dedicate), foglio mensile Excel (prove dedicate), riepilogo di gruppo in Excel.

## Interfaccia (browser)

- `strumenti/giro_interfaccia.cjs`: ogni profilo dimostrativo (Amministratore, HR centrale, Responsabile, Compilatore, Direzione) ha aperto tutte le pagine del proprio menu (26/22/20/12/12 pagine) senza errori di console, di pagina o HTTP, e senza riquadri di errore. Ripetuto dopo ogni gruppo di modifiche, anche sui dati migrati da un archivio 0.11 sintetico.
- Controllo a 390 px di larghezza (telefono): nessuna pagina scorre in orizzontale; la vista «Giorno» del registro e i menu funzionano al tocco.
- Flussi provati con Playwright: primo accesso con codice di attivazione, QR e codici di recupero (modalità aziendale del portale di prova), accesso con codice dell'app, uscita e rientro; registrazione di un turno; importazione Excel (anteprima, scelta della destinazione, conferma, file già importato); fascicolo con tipo di rapporto e dati per i compensi; pagina Collaboratori e compensi; accordo con correzione del teorico; parametri con posti e soglia; scheda «Manuale e video» della guida; scaricamento del foglio mensile Excel dalle Esportazioni.

## Demo pubblica

Costruita con `demo/costruisci_demo.py` (2,6 MB senza Pyodide incluso) e provata in Chromium con `demo/prova_demo.cjs`: avvio del motore nel browser in 2,7 s (Pyodide locale) e 4,6–5,3 s (dalla rete di distribuzione), 18 pagine del Responsabile aperte, una registrazione salvata, un CSV scaricato, nessun errore con la Content Security Policy severa. La demo **non è pubblicata**.

## Migrazione dalla 0.11

Provata con un archivio 0.11 sintetico generato dal codice della 0.11 (`strumenti/archivio_011_di_prova.py`) e con le 13 prove automatiche: archivio di origine intatto, importazione tutto-o-niente, parametri dei mesi, sedi e registrazioni importate, fascicoli e documenti, accordi, posta e promemoria spenti, impronte di approvazioni e sostituzioni, accessi con password, Authenticator (con chiave) e codici di recupero. Il portale migrato è stato percorso per intero dal browser. Nessun archivio aziendale reale è stato migrato.

## Modello Excel mensile

- Il file reale di un mese (fuori dai sorgenti) è stato studiato per intero: fogli, formule, macro VBA, immagini del vademecum (`docs/STUDIO_MODELLO_EXCEL.md`).
- Importazione provata sul file reale: 19 persone, 417 registrazioni, 83 giorni-fascia di pazienti, 13 proposte economiche, 1 cella non riconosciuta elencata; poi un secondo mese sintetico aggiunto alla stessa struttura.
- Revisione indipendente dell'importazione con quattro lenti (fedeltà al file, robustezza del parser con circa 110 file ostili, integrità alla conferma, interfaccia) e verifica di ogni rilievo: **44 rilievi confermati, tutti corretti** e coperti da prove.
- Il foglio mensile generato dal portale è stato aperto con zipfile, convertito in PDF con LibreOffice e controllato a vista (griglia, colori, contatori, spazio ufficio del personale, indicatori, foglio per il consulente, collaboratori).
- Gli indicatori di carico ed efficienza e il prospetto collaboratori sono stati rivisti da un controllore indipendente e corretti.

## Guide

- Manuale d'uso illustrato (HTML autonomo da 10 MB + PDF A4 di 58 pagine con 49 figure, segnalibri e indice con numeri di pagina) generato da `strumenti/guide/manuale.cjs` dalle schermate del portale di prova in modalità aziendale; controllato da un revisore indipendente e rigenerato dopo le correzioni (ordine delle figure, impaginazione, indice, «chi può farlo»). Controlli automatici del generatore: tutte le 26 pagine del portale coperte, nessuna stringa «undefined», nessun errore di console, nessun riferimento esterno nell'HTML.
- 8 videoguide (H.264 1280×720, 30 fps, senza audio, sottotitoli impressi + VTT + trascrizione + copertina), da 74 a 125 secondi, generate da `strumenti/guide/video.cjs`; sincronia dei sottotitoli controllata su fotogrammi estratti.

## Pacchetti

`strumenti/consegna.py` produce lo ZIP unico e il TXT dei sorgenti (anche eseguibile) e li verifica: ricostruzione dal TXT in una cartella temporanea identica ai sorgenti, rifiuto di una cartella già occupata, integrità dello ZIP; esito in `materiali/VERIFICA_PACCHETTO_1.0.0.txt`.

## Non verificato

Server aziendale e HTTPS, rete e carico reali delle sedi, NAS, servizio di posta (nessuna email reale inviata), tracciato del consulente paghe, migrazione di un archivio aziendale reale, tariffe reali dei collaboratori. Tutto ciò che riguarda servizi esterni arriva spento e senza parametri presunti.
