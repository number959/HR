# Aggiornamento 0.11 — processi HR

Sono aggiunti i sei interventi approvati: approvazione mensile, verifica documenti, promemoria, specifiche paghe, copertura turni e uscite/dotazioni. Il portale personale del dipendente non è incluso.

## Aggiornare l’installazione

1. Ferma il servizio; conserva copia completa del programma precedente, del database e della chiave privata. Verifica il backup prima di procedere.
2. Sostituisci soltanto il programma, mantenendo dati, chiave, configurazione di servizio e credenziali esterne nelle rispettive cartelle. Non eseguire `manage.py init` su un archivio esistente.
3. Avvia con i percorsi precedenti: `core.init_db()` effettua una copia prima dell’aggiornamento dallo schema precedente e crea le tabelle additive dello schema 8. I documenti esistenti risultano ricevuti, senza verifica HR presunta.
4. Verifica accessi, fascicoli e presenze. Il percorso di approvazione nasce disattivato per ogni struttura; si attiva dall’apposita pagina come amministratore. I mesi già chiusi rimangono riconoscibili come storico precedente.
5. I promemoria nascono disattivati. Prima di attivarli occorrono SMTP, indirizzi autorizzati, anteprima e conferma. Gli esiti incerti non vanno ritentati senza verifica presso il servizio di posta. `manage.py after-restore` disabilita anche l’automazione.
6. Raccogli dal consulente il tracciato paghe. Il profilo generico non dichiara compatibilità con un fornitore; il formato concordato richiede mappatura e collaudo.

## Funzionamento

- La sede invia il mese, il responsabile verifica, HR approva. Restituzioni e riaperture richiedono nota; dopo l’invio il registro è congelato. Modifiche ai riferimenti invalidano l’impronta della verifica.
- HR verifica i documenti, può richiedere correzioni e consulta lo storico. La sede richiede nuova verifica; scadenza e verifica restano informazioni distinte.
- I promemoria inviano riepiloghi con conteggi ai referenti delle strutture e/o HR centrale, senza dettagli personali. Il ciclo ogni cinque minuti opera solo nel processo server.
- Copertura confronta minimi, pianificato e consuntivo. Le sostituzioni richiedono identità di gruppo già collegate e conferma della sede destinataria; l’accettazione ricontrolla conflitti e permessi.
- Uscite e trasferimenti usano checklist e registro dotazioni. Il completamento non modifica da solo contratto, anagrafica o account esterni.

Guide, tutorial contestuali e videoguide illustrate sono disponibili nella sezione Guide. L’edizione qualità 0.11.1 aggiunge una nuova presentazione con voce di 157 secondi, manuale illustrato e videoguide Full HD; vedere AGGIORNAMENTO_0.11.1.md.

Per i risultati effettivi di collaudo consultare VERIFICA.md. Prima dell’uso reale è necessario il collaudo con server, NAS, servizio SMTP e consulente aziendali.
