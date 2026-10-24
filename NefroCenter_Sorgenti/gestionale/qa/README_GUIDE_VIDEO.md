# Videoguide illustrate Full HD

Le 34 videoguide usano schermate reali della demo con dati sintetici. Ogni scheda presenta una sola istruzione, con testo misurato prima della generazione e una schermata di riferimento. Le immagini non simulano interazioni dal vivo. Questi tutorial sono senza audio; la presentazione con voce è un contenuto distinto.

## Riproduzione e accessibilità

- MP4 H.264, 1920×1080, 30 fotogrammi al secondo, CRF 20, avvio rapido.
- Copertina JPEG Full HD, trascrizione TXT, sottotitoli VTT e capitoli per ciascun argomento.
- Sottotitoli di massimo due righe da 44 caratteri; ogni frase rimane visibile almeno due secondi.
- Tempo di lettura proporzionato al testo, con margine per osservare la schermata. È possibile mettere in pausa.
- Il testo principale delle 296 schede attuali è di 34 pixel. I dialoghi verticali possono essere mostrati in due parti contigue, esplicitamente indicate.

## Rigenerazione

Servono Python 3 con Pillow, FFmpeg/ffprobe e i font DejaVu Sans nel percorso Linux indicato nel renderer. Le 46 catture WebP e il manifest con percorsi relativi sono inclusi in `assets/guide_screens/`. Non occorre l'archivio temporaneo usato durante lo sviluppo.

Da questa cartella applicativa:

```sh
python qa/render_guide_videos.py --sample copertura
python qa/generate_guides.py --videos --only-topic copertura
python qa/generate_guides.py --videos
python qa/validate_guide_media.py
```

Il campione produce soltanto PNG in `qa/guide_frames/quality-sample/`. I video vengono scritti in `assets/guides/`; il manifest e `assets/help_videos.js` descrivono i contenuti al portale. `--screenshots DIRECTORY` permette di usare nuove catture PNG o WebP con lo stesso manifest.

Il renderer usa due lavori concorrenti e due thread FFmpeg per lavoro. Conserva un checkpoint di testo e immagini per riutilizzare i video già terminati dopo un'interruzione. Il file temporaneo MP4 sostituisce il video precedente soltanto a codifica conclusa. I checkpoint e i fotogrammi di lavoro restano locali sotto `qa/guide_frames/quality/`.

`qa/guide_quality_validation.json` contiene l'ultimo controllo di risoluzione, frequenza, durata, capitoli, copertine, sottotitoli, trascrizioni e sorgenti portabili. Il controllo confronta le istruzioni con `docs/help_catalog.json` e usa ffprobe per leggere i file effettivi.
