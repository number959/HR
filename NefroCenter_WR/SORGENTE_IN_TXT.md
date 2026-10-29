# Ricreare i sorgenti dal file TXT

`Codice_Sorgente_NefroCenter_WR_1.0.0.txt` contiene **tutti i file del progetto** in un unico testo UTF-8 (codice, interfaccia, documenti, librerie incluse e, nella versione completa, manuale e videoguide). È anche uno script Python.

## Il modo più semplice

Con Python 3.10 o superiore, dalla cartella in cui si trova il file:

```bash
python Codice_Sorgente_NefroCenter_WR_1.0.0.txt --directory NefroCenter_WR
```

Il comando ricrea la cartella `NefroCenter_WR/` (gestionale, demo, strumenti, documenti) controllando l'impronta SHA-256 di ogni file. Si ferma, senza scrivere nulla, se la cartella scelta esiste e non è vuota o se il TXT è incompleto. Non installa dipendenze, non avvia servizi, non pubblica niente.

Per vedere solo l'elenco dei file: `python Codice_Sorgente_NefroCenter_WR_1.0.0.txt --list`.

## Come è fatto

- `TEXT_FILES`: codice e documenti leggibili, una riga per riga.
- `BINARY_FILES`: impronta di ogni file binario (immagini, PDF, video); `BINARY_CONTENTS`: il contenuto in Base64, una volta sola per contenuto.
- In coda, il programma che ricrea i file.

Il TXT si rigenera con `python strumenti/consegna.py` (dalla cartella `NefroCenter_WR`), che produce anche lo ZIP, l'elenco delle impronte `SHA256SUMS_1.0.0.txt` e il rapporto `VERIFICA_PACCHETTO_1.0.0.txt`. Con `--senza-media` il TXT non contiene manuale e videoguide e pesa pochi megabyte; lo ZIP li contiene sempre.

Restano fuori da ZIP e TXT: dati, chiavi, backup, ambienti virtuali, cache e la build della demo (`demo/dist`, che si ricrea con `demo/costruisci_demo.py`).
