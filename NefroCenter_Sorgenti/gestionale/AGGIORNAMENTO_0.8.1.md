# NefroCenter — Persone e Presenze Web 0.8.1

Revisione del 18 ottobre 2026, ripresa dallo ZIP 0.8 fornito dall’utente. Tutte le 155 impronte SHA256 del pacchetto ricevuto sono risultate corrispondenti prima delle modifiche. Questa revisione conserva architettura, fascicoli HR, autenticazione a due fattori, autorizzazioni e quattro stili.

## Correzioni

| Problema riprodotto | Comportamento corretto |
|---|---|
| Nell’Excel dei fascicoli, ore settimanali e part-time erano testo. | Ore numeriche e percentuale Excel con due decimali; matricole e CAP conservano gli zeri iniziali. I valori mancanti rimangono vuoti. |
| Svuotare un mese e cambiare tipo di esportazione poteva lasciare un campo obbligatorio nascosto, bloccando il download. | I campi non pertinenti sono disabilitati. I prospetti HR della situazione attuale funzionano anche dopo aver cancellato il periodo di un altro prospetto. |
| Passando a un centro senza il ruolo precedentemente selezionato, il registro sembrava vuoto anche se il menu mostrava tutti i ruoli. | Il filtro non disponibile viene azzerato e le persone del centro sono visibili. |
| Aprendo un altro centro dalla dashboard, l’area Dipendenti poteva tentare di riaprire il fascicolo del centro precedente. | Al cambio di centro si azzerano selezione e dati HR in memoria, quindi si carica l’archivio corretto. |
| Un file non SQLite, una directory o un collegamento con nome simile a un backup del giorno poteva impedire la copia giornaliera. | Avvio e controllo orario condividono il filtro dei file pubblicati: nome esatto, file regolare, assenza di collegamenti simbolici, intestazione SQLite. |

Il filtro dei backup non è una nuova scansione completa delle copie già conservate: l’integrità SQLite viene verificata alla creazione, come prima. La verifica diretta di `manage.py after-restore` conferma la revoca di sessioni, attivazioni e recuperi, mantenendo utilizzabile il TOTP con la chiave corretta.

## Avvio e aggiornamento

Per una nuova prova locale seguire [INSTALLAZIONE_WEB.md](INSTALLAZIONE_WEB.md). Usare un archivio dimostrativo separato, creare le proprie credenziali e completare l’attivazione 2FA. Non sono inclusi account operativi preconfigurati.

La 0.8.1 non modifica lo schema del database e non richiede nuove librerie. Per aggiornare un’installazione esistente conservare backup verificato, chiave originale e configurazione, fermare il servizio e usare questa cartella di codice mantenendo i percorsi dati e chiave. Non eseguire nuovamente `init` su un archivio già configurato.

La versione ricevuta è conservata senza modifiche in `rollback/Presenze_Web_v0.8_Originale.zip`, insieme ai rollback 0.7 e 0.6. Per il ripristino dei dati seguire [ROLLBACK.md](ROLLBACK.md).

## Interfacce e prossima verifica

Gli stili Attuale, Spazio di lavoro, Essenziale ed Editoriale restano selezionabili dal menu Stile. Il confronto in `anteprime/CONFRONTO_STILI_v0.8.1.md` usa schermate dell’applicazione reale con dati dimostrativi. Spazio di lavoro offre una navigazione laterale utile per l’uso quotidiano; non è stata imposta una nuova scelta predefinita.

Questa è una revisione collaudata localmente. Installazione sul server aziendale, HTTPS, collegamenti fra sedi e ripristino nell’ambiente effettivo restano da provare. Backup remoto, approvazioni mensili e portale dipendente rimangono proposte separate, non funzioni aggiunte da questa revisione.

Esiti e ambiente effettivi: [VERIFICA.md](VERIFICA.md). Nessuna nuova libreria grafica: CSS e JavaScript nativi, Roboto e Lucide già inclusi; export prodotti da XlsxWriter. Licenze e risorse della consegna originale sono conservate.
