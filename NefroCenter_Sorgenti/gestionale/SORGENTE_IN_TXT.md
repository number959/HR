# Copiare e ricreare il sorgente — edizione qualità 0.11.1

`Codice_Sorgente_NefroCenter_v0.11.1.txt` contiene il codice del gestionale e della demo, insieme alle risorse necessarie: immagini, font, manuale illustrato e video. È testo UTF-8 ed è anche uno script Python autonomo.

## Il modo più semplice

Scarica il TXT e, con Python 3.12 o superiore installato, esegui:

```bash
python Codice_Sorgente_NefroCenter_v0.11.1.txt --directory NefroCenter_Sorgenti
```

In alternativa puoi copiare **tutto** il testo in un editor, salvarlo come `ricrea_nefrocenter.py` in UTF-8 ed eseguire:

```bash
python ricrea_nefrocenter.py --directory NefroCenter_Sorgenti
```

Il file è grande perché contiene anche i video: scaricarlo direttamente evita copie parziali. Se preferisci, lo ZIP del gestionale contiene gli stessi sorgenti senza dover usare il ricostruttore.

## Che cosa succede

Il comando verifica le impronte SHA-256 e ricrea `gestionale/` e `demo/` dentro la cartella scelta. Non installa dipendenze, non avvia servizi, non pubblica siti e rifiuta una cartella già popolata. Per vedere solo l’elenco dei file, senza scrivere nulla:

```bash
python Codice_Sorgente_NefroCenter_v0.11.1.txt --list
```

Nel TXT, `TEXT_FILES` contiene codice e documenti leggibili; `BINARY_FILES` associa ogni risorsa binaria alla sua impronta e `BINARY_CONTENTS` conserva la corrispondente stringa Base64. Risorse identiche usate dal gestionale e dalla demo sono incorporate una sola volta e ricreate nei rispettivi percorsi. Le impronte vengono controllate prima di scrivere i file; una copia incompleta o alterata deve essere scaricata nuovamente.

Sono inclusi i componenti del progetto e le librerie Python distribuite con il software, con le rispettive licenze, oltre ai sorgenti disponibili per generare guide e presentazione. `cryptography` e `tzdata` restano da installare con `requirements.txt`. Non sono inclusi dati aziendali, password operative, chiavi, ambienti virtuali, cronologia Git, output temporanei o archivi ZIP delle vecchie versioni. Le copie per rollback restano nel pacchetto ZIP del gestionale.

Per installare il gestionale ricostruito segui `gestionale/INSTALLAZIONE_IN_BREVE.md`. La cartella `demo/` contiene una demo statica con dati fittizi; le modifiche restano nella sessione di ogni visitatore. L’edizione 0.11.1 aggiorna guide e media; la versione funzionale del backend resta 0.11.
