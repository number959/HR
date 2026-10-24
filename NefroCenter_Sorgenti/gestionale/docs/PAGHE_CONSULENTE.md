# File per il consulente paghe

Il gestionale destinatario non è ancora stato comunicato. Il software include un modello generico e un adattatore configurabile per file CSV/Excel. La compatibilità va verificata con le specifiche e con un’importazione di prova nel gestionale effettivo. Non vengono prodotti cedolini, calcolati contributi o inviati file a servizi esterni.

## Cosa chiedere al consulente

Chiedere il nome del gestionale, nome e versione del tracciato, un file vuoto con le intestazioni e le regole: ordine delle colonne, tipo, campi obbligatori, lunghezze, separatore CSV e decimale, formato delle date, codifica, matricole e causali. Precisare che il file contiene **una riga per fascia a consuntivo**. Se servono righe aggregate, larghezza fissa, campi non disponibili o trasformazioni ulteriori, occorre un adattamento specifico.

## Configurazione

1. In **Paghe**, selezionare il centro e **Tracciato del consulente**.
2. Compilare il destinatario e il riferimento alle specifiche.
3. Leggere la sola intestazione CSV, senza righe di dipendenti, oppure una specifica JSON. Il file deve essere UTF-8, massimo 32 KiB. Il risultato modifica soltanto la bozza.
4. Associare ogni intestazione a un dato, verificare ordine e regole e compilare causali/matricole. Il tracciato deve comprendere matricola, data e causale paghe.
5. Salvare in bozza. Dopo la verifica col consulente, scegliere **Verificato con il consulente**, annotare il riferimento e confermare esplicitamente questa versione.
6. Generare l’anteprima e correggere i controlli bloccanti. Con flusso approvazioni attivo, ogni mese richiede approvazione HR e chiusura. Scaricare e collaudare un mese pilota prima dell’uso operativo.

Le ore mancanti restano vuote. Ore lavorate, crediti delle assenze e conteggi delle assenze sono distinti. Gli zeri iniziali delle matricole sono conservati. Nel tracciato consulente i prefissi che Excel potrebbe interpretare come formule vengono bloccati, senza alterare silenziosamente il codice richiesto.

Il CSV applica separatori, codifica e date configurati. Excel mantiene numeri e date come celle tipizzate e include un foglio informativo. L’anteprima controlla tutte le righe anche quando mostra soltanto le prime 100; fino a 200 anomalie vengono visualizzate. Modificare presenze o modello invalida il download della precedente anteprima.

## Specifiche trasferibili

**Scarica le specifiche salvate** produce un JSON `nefrocenter.payroll-spec.v1` con metadati del formato, intestazioni, associazioni dei campi e regole. Esclude presenze, dati dei dipendenti, matricole individuali e mappature delle causali. Il JSON può essere riletto nella stessa pagina e richiede una nuova verifica prima della conferma.

[ESEMPIO_SPECIFICA_PAGHE.json](ESEMPIO_SPECIFICA_PAGHE.json) è un esempio da concordare, con destinatario e versione lasciati vuoti. Non rappresenta il formato certificato di un gestionale.

Le versioni salvate sono conservate e le esportazioni vengono registrate nello storico con periodo, versione e impronta dei dati. Il file effettivo deve essere consegnato al consulente tramite i canali aziendali scelti dall’ufficio HR.
