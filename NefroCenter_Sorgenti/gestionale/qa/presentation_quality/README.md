# NefroCenter — presentazione v0.11, revisione qualità

Presentazione di 2 minuti e 37 secondi costruita su schermate reali della demo, con dati esclusivamente fittizi. Versioni con voce italiana sintetica e senza audio; nessuna musica. Le schermate non sono una registrazione di dati aziendali né una ricostruzione inventata dell’interfaccia.

## Qualità e contenuto

- Full HD 1920×1080, 30 fotogrammi al secondo, H.264 CRF18, formato YUV420p e MP4 ottimizzato per l’avvio nel browser.
- Titoli fermi, una riga di spiegazione, pannelli dell’app grandi e dettagli dei moduli ingranditi. Le leggere panoramiche mostrano i contenuti senza muovere i titoli.
- Undici capitoli, comprese le funzioni aggiunte alla v0.11: verifica documenti, approvazioni, copertura, promemoria, specifiche paghe e uscite.
- Voce sintetica italiana ElsaNeural, ritmo naturale senza accelerazione successiva; normalizzazione a circa −16 LUFS, AAC 192 kbit/s a 48 kHz.
- Sottotitoli VTT sincronizzati alle parole, con punteggiatura originale, massimo due righe e 42 caratteri per riga. Trascrizione e capitoli separati.

## Sorgenti

`scenes.json` contiene testi e scene; `timeline.json` contiene le durate effettive. `audio/` conserva i segmenti MP3 e i confini delle parole ricevuti dal servizio vocale. `source/` conserva copie delle schermate usate e del logo. `build_audio.py` costruisce la traccia e i sottotitoli; `build_video.py` crea i segmenti e li unisce. I file temporanei di rendering non sono necessari nel pacchetto dei sorgenti.

Per ricostruire in Linux servono Python 3.12, Pillow, edge-tts 7.3.1, FFmpeg/ffprobe e Liberation Sans (`fonts-liberation`). I segmenti vocali salvati permettono di ricostruire senza contattare il servizio vocale; modificare i testi richiede una nuova sintesi e una connessione HTTPS autorizzata. I comandi preservano proxy e certificati dell’ambiente.

Il pacchetto portabile dei sorgenti scrive gli output in `output/`.

Preparazione di esempio su Debian/Ubuntu:

```sh
sudo apt install ffmpeg fonts-liberation python3-venv
python3 -m venv .venv
.venv/bin/pip install -r requirements-media.txt
.venv/bin/python build_audio.py
.venv/bin/python build_video.py
.venv/bin/python validate.py
```

Con i testi originali, i segmenti in `audio/` vengono riutilizzati. La ricostruzione della traccia audio da questo pacchetto è stata confrontata con l’originale: stesso SHA-256 del WAV normalizzato. I percorsi di input e output sono relativi alla cartella dei sorgenti. Eseguire prima `python build_audio.py`, poi `python build_video.py`. Per una prova del solo capitolo: `python build_video.py --only dashboard`. `--force` rigenera i segmenti anche se già presenti.

## Verifica

`verification.json` registra risoluzione, frame rate, durata, conteggio capitoli, decodifica completa, struttura dei sottotitoli e misura del volume. `validate.py` effettua questi controlli sui due MP4. Il controllo visivo dei fotogrammi e delle inquadrature accompagna le verifiche tecniche.
