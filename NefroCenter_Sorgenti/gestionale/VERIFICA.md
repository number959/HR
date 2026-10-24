# Verifica — edizione qualità 0.11.1

Edizione documentale e multimediale del software funzionale 0.11; schema database 8 invariato. Controlli eseguiti il 23–24 ottobre 2026, con dati sintetici.

## Gestionale e permessi

La suite completa della versione di base aveva superato 254 test Python in 127,275 secondi. Per questa revisione sono stati rieseguiti i 9 test HTTP v09/v011 e il nuovo test degli asset illustrati (10 complessivi), inclusi PDF, immagini WebP/JPEG, video e percorsi non ammessi: tutti superati. Il percorso browser completo dell’app è nuovamente superato, compresi accessi e 2FA, salvataggi HR, permessi, quattro stili, tutte le sei funzioni della 0.11, video/capitoli, aiuto contestuale che conserva le modifiche non salvate, tastiera e pagine a 390/320 px.

Le API della demo sono state provate per i cinque ruoli. La nuova regressione verifica che il responsabile non possa configurare le approvazioni: risposta 403 e configurazione invariata. Il percorso browser attraversa tutte le pagine consentite a 1400/390 px; la schermata ruoli è verificata anche a 768/320 px.

I log di sviluppo sono `qa/web-quality.log`, `qa/browser-quality.log` e quelli della demo. I file temporanei e i log di sviluppo non fanno parte della distribuzione; i rapporti JSON dei media e gli script delle prove sono inclusi per verifiche ripetibili.

## Guide e PDF

Catalogo: 34 procedure, 323 impostazioni, sette percorsi per ruolo. Ogni procedura include prerequisiti, passaggi, risultato atteso, esempio e problemi frequenti. La guida contiene schermate reali della demo con dati interamente fittizi; le immagini sono ingrandibili.

Manuale PDF di 42 pagine e presentazione HR di 11 pagine: controllati indice e segnalibri, struttura con tag, assenza di pagine spurie o sforamenti e presenza dei 34 argomenti. Gli HTML sono autonomi, con immagini incorporate. Il riferimento delle 323 impostazioni offre ricerca e filtri; controllato anche a 390 px. Rapporto conclusivo: `qa/manual-delivery-validation.json`; verifiche dettagliate in `qa/manual-validation.json` e `qa/manual-pdf-validation.json`.

## Video

Tutte le 34 videoguide sono 1920×1080 a 30 fps, senza audio, con copertina, capitoli, VTT e trascrizione. Controllati file effettivi tramite ffprobe, testo delle 296 schede (minimo 34 px), sottotitoli su massimo due righe da 44 caratteri e permanenza minima 3,071 secondi. Durata complessiva: 60 minuti e 14 secondi. Le 46 schermate WebP e il manifest usano percorsi portabili. Rapporto: `qa/guide_quality_validation.json`.

Presentazione generale: 157 secondi, 1920×1080 a 30 fps, 4710 fotogrammi, 11 capitoli e 40 sottotitoli. Entrambi gli MP4 sono stati decodificati integralmente senza errori. La versione con voce sintetica italiana misura −16,11 LUFS e picco −1,47 dBTP. Le impronte SHA-256 dei file verificati sono in `qa/presentation_quality/verification.json`; sorgenti di montaggio, audio già generato e schermate sono inclusi nella stessa cartella.

## Controlli finali della demo

Guida verificata a 1400/390/320 px: sette percorsi ordinati, ricerca, 34 procedure, 323 impostazioni, navigazione avanti/indietro, FAQ, immagini, PDF, sottotitoli e salto ai capitoli prima del primo caricamento. Presentazione di 157 secondi verificata alle stesse larghezze, con riproduzione, sottotitoli, download, 11 capitoli, chiusura e pausa.

Corretto il launcher locale `avvia_demo.py` per supportare richieste Range sugli MP4: quattro test superati per intervalli, suffissi, risposte 206/416, HEAD e If-Range. Questo permette i salti ai capitoli anche nella demo scaricabile. Rapporto complessivo incluso: `qa/media-quality-verification.json`.

## Installazione e limiti

Il gestionale operativo non è installato su un server aziendale. La demo pubblica usa copie separate per visitatore, dati sintetici e simulazioni: non è un archivio HR condiviso tra le persone invitate. Posta, NAS e tracciato paghe aziendali restano da configurare e collaudare; nessuna email reale è stata inviata. Approvazioni e promemoria restano disattivati per impostazione iniziale nel gestionale operativo.

Il collaudo nel contenitore Linux non sostituisce quello sul server aziendale. Per installare seguire `INSTALLAZIONE_IN_BREVE.md` e `INSTALLAZIONE_WEB.md`. Gli identificativi della pubblicazione effettiva sono in `STATO_PROGETTO.json`.

## Pacchetti

Gli archivi dell’edizione qualità usano il suffisso v0.11.1. Il TXT contiene codice leggibile e risorse binarie deduplicate, ricostruisce gestionale e demo e controlla ogni SHA-256 prima di scrivere. La verifica effettiva della ricostruzione, del rifiuto di cartelle già popolate e dei due ZIP è registrata nel file di consegna `VERIFICA_PACCHETTO_v0.11.1.txt`. Le versioni precedenti restano disponibili per rollback.
