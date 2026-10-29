# Paghe: il file per il consulente

Il gestionale del consulente paghe **non è ancora stato comunicato**. Il portale ha un tracciato generico in bozza e un profilo configurabile per il tracciato del consulente (CSV o Excel). La compatibilità va verificata con le specifiche del consulente e con un'importazione di prova nel suo gestionale. Il portale non produce cedolini, non calcola contributi e non invia file a servizi esterni.

## Cosa chiedere al consulente

Nome del gestionale, nome e versione del tracciato, un file vuoto con le sole intestazioni e le regole: ordine delle colonne, tipo (testo, intero, decimale, data), campi obbligatori, lunghezze massime, separatore CSV e decimale, formato delle date, codifica, matricole e causali paghe. Il file del portale contiene **una riga per ogni fascia a consuntivo**; se servono righe aggregate, campi non disponibili o trasformazioni ulteriori, occorre un adattamento.

## Configurazione (Paghe, profili HR e Amministratore)

1. Scegliere la struttura e aprire **Tracciato del consulente**: indicare destinatario, nome e versione del tracciato, riferimento alle specifiche.
2. Leggere la sola riga di intestazione del CSV del consulente (senza righe di dipendenti) oppure una specifica JSON `nefrocenter.payroll-spec.v1` (UTF-8, massimo 32 KiB). La lettura modifica solo la bozza.
3. Associare ogni intestazione a un dato del portale, controllare ordine e regole, compilare le causali paghe e le matricole. Il tracciato deve comprendere almeno **matricola, data e causale paghe**.
4. Salvare come **Bozza da concordare**. Dopo la verifica con il consulente passare a **Verificato con il consulente**, annotando il riferimento della verifica (almeno 8 caratteri) e confermando esplicitamente il profilo.
5. Generare l'**anteprima** del periodo, correggere i controlli bloccanti (ore mancanti, causali senza codice, matricole mancanti) e scaricare il file (CSV o Excel). Lo scaricamento chiede la conferma di sicurezza ed è legato all'impronta dei dati: se presenze o tracciato cambiano, l'anteprima va rigenerata.
6. Collaudare un mese pilota nel gestionale del consulente prima dell'uso operativo. Con l'approvazione mensile attiva, il mese deve essere approvato e chiuso.

Gli zeri iniziali delle matricole sono conservati; i valori che Excel interpreterebbe come formule vengono bloccati; ore lavorate, crediti delle assenze e conteggi delle assenze restano distinti. Il CSV usa separatori, codifica e formato data configurati; l'Excel ha celle tipizzate e un foglio informativo.

## Specifiche trasferibili

**Scarica le specifiche attuali (JSON)** produce il JSON `nefrocenter.payroll-spec.v1` con destinatario, nome e versione del tracciato, intestazioni, associazioni e regole, senza dati delle persone. Lo stesso file si può rileggere in un'altra struttura o installazione; richiede una nuova verifica prima della conferma.

Le versioni del tracciato sono conservate; ogni scaricamento viene registrato nello storico con periodo, versione e impronta dei dati. La consegna del file al consulente avviene con i canali scelti dall'ufficio HR.
