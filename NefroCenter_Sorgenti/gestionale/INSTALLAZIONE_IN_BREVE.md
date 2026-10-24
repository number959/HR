# Dove installarlo e cosa serve — NefroCenter 0.11 · edizione qualità 0.11.1

**Il software si installa una sola volta su un server aziendale centrale.** Le sedi e l’ufficio HR lo aprono dal browser, usando lo stesso indirizzo HTTPS. I documenti caricati dalle sedi vengono conservati nell’archivio centrale e sono consultabili dagli utenti autorizzati, incluso il nuovo ruolo **HR centrale**.

## Cosa preparare

- Un server o PC aziendale Linux o Windows, acceso durante l’utilizzo, con disco locale, spazio per documenti e backup e rete affidabile. Linux con servizio automatico è la scelta consigliata.
- **Python 3.12 o 3.13 a 64 bit** e le dipendenze `cryptography` e `tzdata` indicate in `requirements.txt`. Gli altri componenti Python necessari sono inclusi nel pacchetto.
- Un indirizzo HTTPS raggiungibile dalle sedi, tramite VPN aziendale oppure dominio e reverse proxy configurati dal tecnico. Il proxy gestisce il certificato e inoltra al servizio locale. La porta applicativa 8080 resta interna al server.
- Browser aggiornati sui PC delle sedi e di HR; un’app Authenticator per il secondo fattore di ciascun account. Non occorre installare programmi sulle postazioni.
- Una cartella del **NAS**, accessibile all’account del servizio, per la seconda copia dei backup. Il tecnico deve indicare il percorso reale e verificarne l’accesso. Non sono incluse credenziali NAS preconfigurate.
- Per spedire email, un servizio **SMTP aziendale compatibile**, con TLS, un mittente autorizzato e i parametri forniti dal tecnico. Il fornitore non è ancora definito: modelli, liste e bozze funzionano anche con l’invio disattivato. La password SMTP resta nell’ambiente del server, non nel browser. Vedere `docs/SMTP_CONFIGURAZIONE.md`.

Non occorrono nuovi abbonamenti software se server, rete e NAS sono già disponibili; restano la gestione e manutenzione aziendale. Un hosting che serve solo pagine statiche non esegue questa applicazione.

## Come si attiva

1. Il tecnico estrae il pacchetto in una cartella del server, crea un ambiente virtuale Python e installa `requirements.txt`.
2. **Solo per una nuova installazione**, esegue `manage.py init` con i percorsi dell’archivio e della chiave privata. Il comando crea il primo centro, l’amministratore e il codice di attivazione 2FA. Per un aggiornamento conserva i dati e la chiave esistenti e segue la guida della versione: non ripete l’inizializzazione.
3. Configura avvio automatico, HTTPS e accesso dalla rete aziendale. Prova il primo accesso e un caricamento da una sede pilota.
4. L’amministratore crea account nominativi per responsabili, compilatori e **HR centrale**. HR centrale vede i fascicoli e i documenti di tutti i centri, senza gestire utenti e impostazioni tecniche del server.
5. In **Backup ed esportazioni** configura la seconda copia sul NAS, esegue **Copia e prova ripristino** e verifica l’esito. La copia NAS rimane disattivata finché non viene impostata una destinazione valida.
6. Compila **Strutture** con i recapiti delle sedi. Quando il servizio di posta è disponibile, l’amministratore configura e abilita SMTP da **Comunicazioni → Servizio di posta**. Gli invii manuali richiedono anteprima, bozza e conferma; la demo online simula soltanto la spedizione.

7. Attiva **Approvazione mese** solo nelle strutture coinvolte nel processo concordato con HR. Per i promemoria automatici, configura prima SMTP, poi apri **Promemoria**, verifica l’anteprima e conferma gli indirizzi. Il server deve rimanere acceso all’orario previsto; l’orario segue Europe/Rome.
8. Chiedi al consulente paghe la specifica del file: intestazioni, causali, date e codifica. Importala in **Paghe**, completa la mappatura e collauda un file prima di usarlo operativamente.

## Dove tenere i file

| Contenuto | Posizione consigliata |
|---|---|
| Programma | Cartella dedicata sul server; su Linux, per esempio `/opt/presenze-web` |
| Database e documenti | Disco locale del server; per esempio `/var/lib/presenze-web` |
| Copie completate del backup | Cartella separata sul NAS, configurata nell’applicazione |
| Chiave `server.key` | Cartella riservata separata dai dati, con una copia protetta custodita dall’IT |

**Non usare il NAS come sede del database attivo.** Vi si copiano i backup completati e verificati. I documenti sono inclusi nel backup SQLite; la chiave `server.key`, necessaria per recuperare i segreti 2FA, va conservata separatamente. Una prova tecnica del backup non sostituisce il collaudo completo del ripristino e degli accessi sul server aziendale.

Per comandi e configurazione dettagliati: [INSTALLAZIONE_WEB.md](INSTALLAZIONE_WEB.md). Per gli utenti: **Guida** nel portale, **Aiuto pagina**, videoguide illustrate Full HD senza audio, il manuale PDF illustrato scaricabile dalla Guida, oppure [GUIDE_UTENTE.md](GUIDE_UTENTE.md).
