#!/usr/bin/env python3
"""Produce manuale, catalogo JS e vere videoguide MP4 locali da un'unica fonte.

Uso: python qa/generate_guides.py [--videos] [--only-topic ID] [--screenshots DIRECTORY]
Pillow e FFmpeg sono strumenti di produzione; non servono al software installato.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPICS = []
SETTINGS = []


def topic(key, title, audience, goal, steps, result, errors, selectors=()):
    TOPICS.append(dict(id=key, title=title, audience=audience, goal=goal, steps=steps,
                       result=result, errors=errors, tour=[dict(selector=a, text=b) for a, b in selectors]))


def settings(topic_id, section, rows):
    for row in rows.strip().splitlines():
        key, label, effect, example = row.split('|', 3)
        SETTINGS.append(dict(id=key, topic=topic_id, section=section, label=label, effect=effect, example=example))


topic('avvio', 'Primo accesso e orientamento', 'Tutti gli utenti con un account nominativo',
      'Entrare dal browser e riconoscere centro, mese e funzioni disponibili.', [
          'Apri l’indirizzo HTTPS comunicato dall’azienda. Servono nome utente, password iniziale e codice di attivazione forniti dall’amministratore.',
          'Al primo ingresso inserisci il codice di attivazione, collega un’app Authenticator tramite QR e verifica il codice a 6 cifre. Scegli una password personale di almeno 12 caratteri.',
          'Conserva i codici di recupero in un luogo riservato, separato dal telefono. Un codice di recupero può essere usato una sola volta.',
          'Nei successivi accessi inserisci password e codice Authenticator. Controlla il centro in alto e il mese prima di registrare dati.',
          'Usa Guida per cercare una procedura o un’impostazione. Aiuto pagina apre il tutorial pertinente senza abbandonare il lavoro. Esci termina l’accesso dal dispositivo.'
      ], 'Il portale mostra solo centri e azioni autorizzati al tuo account.',
      ['Codice Authenticator rifiutato: verifica che l’orologio del telefono sia automatico e usa un codice nuovo.',
       'Codice di attivazione scaduto: chiedi all’amministratore una nuova attivazione. I codici di accesso non vengono spediti automaticamente per email.',
       'Rete assente: le modifiche non si salvano offline. Alla riconnessione ricarica i dati prima di modificarli.'],
      [('#centerSelect', 'Controlla qui la sede su cui stai lavorando.'), ('#monthPick', 'Il mese determina registro, controlli e accordi.'), ('#account', 'Password, Authenticator e codici di recupero sono in Sicurezza · 2FA.')])
topic('dashboard', 'Dashboard del gruppo', 'Tutti, limitatamente ai centri autorizzati',
      'Capire quali centri hanno compilato il mese e aprire il registro giusto.', [
          'Scegli il mese in alto. La dashboard riunisce i centri accessibili e si aggiorna ogni minuto.',
          'Leggi ore consuntive, turni e mesi chiusi. Le ore includono solo registrazioni con orari; un turno senza orari resta comunque un turno.',
          'Nella tabella confronta compilazione, persone, ore e ultima attività. Apri centro porta alle presenze della sede scelta.',
          'Premi Aggiorna dopo una chiamata con la sede. Per correggere le anomalie apri Da completare.',
          'Se disponibile, Esporta CSV scarica il riepilogo dei centri autorizzati per il mese selezionato.'
      ], 'Hai una fotografia del mese e puoi raggiungere il centro da verificare.',
      ['Ore basse non significano necessariamente poche presenze: controlla i turni senza orari.', 'Un centro mancante può dipendere dalle assegnazioni del tuo account.'],
      [('#monthPick', 'Scegli il mese del confronto.'), ('#refreshDashboard', 'Richiedi l’aggiornamento dei dati condivisi.'), ('[data-dash-center]', 'Apri il registro di questo centro.')])
topic('completare', 'Da completare', 'Ogni utente vede le attività consentite dal proprio ruolo',
      'Trovare anomalie e lavoro ancora aperto senza visitare tutte le pagine.', [
          'Apri Da completare e verifica il mese. Le segnalazioni sulle presenze seguono il mese; le scadenze HR riguardano la situazione attuale.',
          'Usa i filtri disponibili per centro, tipo di problema o ricerca. Leggi persona, data e motivo prima di intervenire.',
          'Apri la segnalazione per raggiungere il registro, il fascicolo o il controllo del mese. Per gli orari mancanti compila ingresso, uscita e pausa reali.',
          'Per un pianificato senza consuntivo verifica prima se il turno è stato svolto: il pianificato non diventa automaticamente lavoro effettivo.',
          'Per documenti e onboarding aggiorna il fascicolo e salva. Torna a Da completare e aggiorna per verificare l’esito.'
      ], 'La segnalazione scompare o cambia quando i dati che l’hanno generata sono stati corretti.',
      ['Una segnalazione su una data futura può essere una pianificazione normale: controlla la data.', 'Non vedi un fascicolo HR: chiedi un account autorizzato, senza condividere credenziali.'])
topic('presenze', 'Presenze: pianificato e consuntivo', 'Compilatori, responsabili e amministratori secondo i permessi del centro; lettori in consultazione',
      'Registrare un turno o un’assenza per persona, giorno e fascia.', [
          'Seleziona centro e mese. Scegli Consuntivo per quanto realmente svolto oppure Pianificato per i turni previsti.',
          'Cerca la persona o filtra il ruolo. Su schermi piccoli usa 7 giorni e le frecce; i contatori continuano a riguardare tutto il mese.',
          'Seleziona la cella all’incrocio fra persona, fascia e giorno. Scegli una causale ammessa per quella fascia.',
          'Per lavoro inserisci gli orari reali e la pausa se autorizzato. Per un turno notturno indica correttamente l’uscita nel giorno successivo. Seleziona una sede esterna solo quando pertinente.',
          'Salva e verifica il simbolo nella cella. Assenze e riposi restano distinti dai turni lavorati; il credito di un’assenza non è lavoro svolto.',
          'Per correggere apri nuovamente la cella. Elimina solo una registrazione errata e solo se il tuo account lo permette.'
      ], 'Il salvataggio rende immediatamente disponibile la registrazione sul server centrale.',
      ['Mese chiuso: serve la riapertura motivata da un responsabile autorizzato.', 'Campo disabilitato: il parametro del compilatore è protetto; chiedi al responsabile.', 'Dati cambiati da un’altra sessione: ricarica e confronta prima di ripetere il salvataggio.'],
      [('#centerSelect', 'Conferma il centro prima di scrivere.'), ('#monthPick', 'Controlla mese e stato aperto/chiuso.'), ('#actual', 'Consuntivo contiene quanto è avvenuto.'), ('#planned', 'Pianificato contiene ciò che è previsto.'), ('#gridWindow', 'Passa a 7 giorni per lavorare su uno schermo piccolo.'), ('[data-day]', 'Questa cella identifica una persona, una data e una fascia.')])
topic('dipendenti', 'Dipendenti e fascicolo HR', 'Responsabili dei centri assegnati, HR centrale e amministratori',
      'Creare o completare un fascicolo amministrativo e ritrovare allegati e scadenze.', [
          'Scegli il centro e apri Dipendenti. Cerca per nome, matricola o reparto e filtra lo stato; Nuovo dipendente crea un’anagrafica nel centro.',
          'Apri il fascicolo e completa Anagrafica, Recapiti, Rapporto di lavoro, Amministrazione e Qualifiche. Nel catalogo della Guida trovi l’effetto di ogni campo.',
          'Salva il fascicolo: al primo salvataggio viene creata la checklist onboarding usando il modello del centro e la data d’ingresso.',
          'Apri Onboarding per aggiornare le attività, Documenti per allegare file e Scadenze per verificare le date registrate.',
          'Presenze della persona e Accordo del mese aprono le rispettive funzioni mantenendo il collegamento al dipendente. Salva le modifiche prima di uscire.'
      ], 'Fascicolo e allegati sono sul server centrale e disponibili a HR centrale senza invii separati.',
      ['Matricola già utilizzata: verifica se la persona esiste nel centro.', 'Codice fiscale o IBAN non valido: ricontrolla il documento originale. La verifica di formato non certifica l’identità.', 'Bozza incompleta: i campi personalizzati richiesti possono rimanere vuoti, ma vengono segnalati.'],
      [('#hrSearch', 'Cerca un fascicolo senza crearne un doppione.'), ('#hrNew', 'Crea un fascicolo nel centro selezionato.'), ('#hrSettings', 'Il modello determina le checklist dei nuovi fascicoli.'), ('#hrSave', 'Salva tutte le sezioni anagrafiche del fascicolo.')])
for key, title, goal, steps, result in [
    ('anagrafica', 'Fascicolo: anagrafica', 'Identificare correttamente la persona e la sua presenza nel registro.', ['Nel fascicolo apri Anagrafica e confronta nome, cognome, codice fiscale e dati di nascita con il documento.', 'Imposta Nome completo nel registro, Matricola e Ruolo nelle presenze. La matricola deve essere unica nel centro.', 'Indica Stato del rapporto e Abilitato alla compilazione delle presenze separatamente: lo stato descrive il rapporto; la spunta controlla la disponibilità nel registro.', 'Completa tipo, numero, ente, rilascio e scadenza del documento. Salva fascicolo e apri Scadenze per verificare la data.'], 'I dati identificativi sono salvati e la scadenza del documento è consultabile.'),
    ('recapiti', 'Fascicolo: recapiti', 'Mantenere contatti e indirizzi utili all’amministrazione.', ['Apri Recapiti e inserisci la residenza completa: indirizzo, CAP, comune, provincia e Paese.', 'Indica il domicilio solo se diverso. Compila email personale, telefono, email aziendale e PEC quando pertinenti.', 'Inserisci un contatto di emergenza solo se previsto dalle procedure aziendali, con il relativo telefono.', 'Salva il fascicolo. Il salvataggio dei recapiti non invia messaggi; le comunicazioni e i promemoria hanno pagine e configurazioni dedicate.'], 'L’ufficio autorizzato ritrova i recapiti aggiornati nello stesso fascicolo.'),
    ('contratto', 'Fascicolo: rapporto di lavoro', 'Registrare gli estremi amministrativi del rapporto attuale.', ['Apri Rapporto di lavoro e inserisci società, reparto, responsabile, tipologia, CCNL, livello e mansione.', 'Indica ingresso, eventuale fine contratto e fine prova. Le date di fine non possono precedere l’ingresso.', 'Compila ore settimanali e part-time, poi riferimento contratto, centro di costo, sede, badge e tutor se disponibili.', 'Salva fascicolo. Per conservare cambi con decorrenze usa anche Storico contratti in Personale di gruppo; per le tariffe del mese usa Accordi e calcoli.'], 'Il fascicolo riporta le informazioni attuali; il calcolo mensile richiede un accordo confermato.'),
    ('amministrazione', 'Fascicolo: amministrazione', 'Conservare i riferimenti necessari al pagamento e al consulente.', ['Apri Amministrazione e indica referente paghe e modalità di pagamento.', 'Se necessario inserisci IBAN, intestatario e banca verificandoli sul documento fornito dalla persona.', 'Inserisci Partita IVA solo se pertinente al rapporto.', 'Salva fascicolo. Il software controlla il formato e il controllo numerico IBAN; non effettua pagamenti.'], 'I riferimenti sono disponibili agli utenti HR autorizzati.'),
    ('qualifiche', 'Fascicolo: qualifiche e campi del centro', 'Seguire verifiche amministrative, abilitazioni e dati aggiuntivi.', ['Apri Qualifiche e registra ordine o albo, numero e l’eventuale scadenza pertinente.', 'Indica la scadenza del titolo di soggiorno/lavoro solo quando necessaria e la prossima verifica amministrativa.', 'Compila i campi personalizzati del centro rispettando il tipo: testo, data, numero o Sì/No.', 'Usa le note per riferimenti amministrativi pertinenti e salva. Diagnosi e referti rimangono nei sistemi del medico competente.'], 'Le date salvate alimentano le scadenze del fascicolo; i campi richiesti mancanti restano evidenziati.')
]:
    topic(key, title, 'Utenti autorizzati al fascicolo HR', goal, steps, result,
          ['Se il salvataggio segnala un campo non valido, correggilo nella sezione indicata e salva nuovamente.', 'Una modifica alla scheda non è salvata finché non premi Salva fascicolo.'],
          [(f'[data-hr-section="{key}"]', f'Apri {title.split(": ", 1)[1]}.'), ('#hrSave', 'Conferma il salvataggio del fascicolo.')])
topic('onboarding', 'Fascicolo: onboarding', 'Utenti autorizzati al fascicolo HR',
      'Tenere traccia delle attività d’ingresso senza confonderle con adempimenti inviati.', [
          'Salva prima il nuovo fascicolo con la data d’ingresso: il programma copia il modello del centro e calcola le scadenze relative.',
          'Apri Onboarding e leggi fase, responsabile, scadenza e stato di ogni attività. Premi Aggiorna sull’attività da lavorare.',
          'Scegli Da fare, In corso, Completata o Non applicabile. Inserisci responsabile, data e nota; Non applicabile richiede una motivazione.',
          'Salva attività e verifica il progresso. Completata e Non applicabile concorrono al conteggio delle attività concluse.',
          'Quando cambia l’ingresso o il modello, aggiorna le attività già esistenti singolarmente: il programma non ricalcola le loro scadenze.'
      ], 'Lo storico riporta chi ha aggiornato l’attività e la checklist rende visibile il lavoro aperto.',
      ['Il fascicolo non è ancora salvato: salva prima la scheda.', 'La checklist organizza il lavoro ma non invia comunicazioni obbligatorie né sostituisce le verifiche dei referenti.'],
      [('[data-hr-section="onboarding"]', 'Apri le attività d’ingresso.'), ('[data-hr-task]', 'Aggiorna questa attività con stato e motivazione.')])
topic('documenti', 'Documenti da remoto e consultazione HR', 'Caricamento e consultazione: responsabili autorizzati, HR centrale e amministratori',
      'Allegare dalla sede e permettere all’ufficio HR centrale di visionare lo stesso documento.', [
          'Dalla sede remota entra nello stesso portale aziendale, seleziona centro e dipendente, salva il fascicolo se nuovo e apri Documenti.',
          'Scegli un PDF, PNG o JPEG di massimo 6 MiB. Usa un nome comprensibile, una categoria pertinente e, se utile, una scadenza.',
          'Premi Allega al fascicolo e attendi la conferma. Il file è registrato nel database centrale con autore, data e impronta di integrità.',
          'HR centrale accede con il proprio account, apre l’area Documenti HR e filtra per centro o persona. Visualizza apre l’anteprima; Scarica conserva una copia locale autorizzata.',
          'Controlla documento, categoria e scadenza. Per sostituire un file carica quello corretto e rimuovi l’errato soltanto con la motivazione richiesta.'
      ], 'HR centrale può vedere gli allegati caricati dalle sedi senza ricevere email o copie separate.',
      ['Formato rifiutato: non basta cambiare l’estensione; esporta davvero in PDF o immagine ammessa.', 'File oltre 6 MiB: riduci la scansione o dividila in documenti pertinenti.', 'File appena caricato non visibile: aggiorna l’elenco e controlla centro/persona; non creare archivi separati per le sedi.', 'La rimozione dal fascicolo non cancella le copie presenti nei backup precedenti.'],
      [('[data-hr-section="documenti"]', 'Apri gli allegati della persona.'), ('#hrDocumentFile', 'Seleziona un file PDF, PNG o JPEG entro 6 MiB.'), ('#hrDocumentCategory', 'La categoria facilita la ricerca centrale.'), ('#hrUpload', 'Carica sul server e attendi la conferma.')])
topic('scadenze', 'Fascicolo: scadenze', 'Utenti autorizzati al fascicolo HR',
      'Ritrovare contratti, documenti e attività da rivedere.', [
          'Apri Scadenze nel fascicolo per vedere tutte le date della persona; l’elenco Dipendenti riassume le scadenze vicine e già trascorse.',
          'Leggi oggetto, data e stato. Una data trascorsa è un invito alla verifica, non la prova automatica di una violazione.',
          'Premi Apri sezione per raggiungere l’origine: contratto, qualifiche, onboarding, anagrafica o documenti.',
          'Aggiorna il dato dopo la verifica e salva nella sua sezione. Ritorna alle scadenze per controllare il risultato.'
      ], 'Le scadenze riflettono le date salvate, senza doverle ricopiare in un secondo elenco.',
      ['Data assente: completa il campo nel fascicolo o nel documento.', 'Attività completata non compare più come aperta: ritrovala nella sezione Onboarding.'],
      [('[data-hr-section="scadenze"]', 'Apri le scadenze della persona.'), ('[data-hr-deadline-section]', 'Raggiungi il campo che genera questa scadenza.')])
topic('modellohr', 'Modello onboarding e campi personalizzati', 'Responsabili autorizzati, HR centrale e amministratori',
      'Preparare le attività e i campi dei nuovi fascicoli del centro.', [
          'In Dipendenti premi Modello onboarding. Verifica il centro: ogni centro ha il proprio modello.',
          'Per ogni attività indica fase, descrizione, responsabile e giorni rispetto all’ingresso. Esempio: −7 significa una settimana prima, 0 il primo giorno, 30 un mese circa dopo.',
          'Aggiungi o rimuovi attività secondo le procedure concordate. Sono ammessi da 1 a 80 compiti.',
          'Aggiungi campi personalizzati, massimo 40, scegliendo etichetta, tipo e Richiesto. Un campo richiesto incompleto viene segnalato ma il fascicolo può essere salvato in bozza.',
          'Salva modello protetto. Le attività si copiano nei nuovi fascicoli; i fascicoli esistenti conservano la propria checklist.'
      ], 'I nuovi fascicoli usano il modello aggiornato; rimuovere una definizione non elimina i valori storici.',
      ['Dati modificati da un’altra sessione: riapri il modello e ripeti solo le modifiche ancora necessarie.', 'Modifica di data ingresso dopo la creazione: le attività esistenti non si rischedulano automaticamente.'],
      [('#hrSettings', 'Apri il modello del centro.'), ('#hrAddTemplateTask', 'Aggiungi un’attività al modello.'), ('#hrAddCustom', 'Aggiungi un campo amministrativo.'), ('#hrSaveTemplate', 'Salva il modello per i nuovi fascicoli.')])
topic('personale', 'Personale di gruppo e storico contratti', 'HR centrale e amministratori; funzioni di sede secondo autorizzazione',
      'Riconoscere una stessa persona fra più sedi e conservare le decorrenze contrattuali.', [
          'Apri Personale di gruppo e cerca la persona. Le anagrafiche di sede rimangono riconoscibili con centro e matricola.',
          'Per associare due anagrafiche verifica documenti, codice fiscale e persona reale. Un nome uguale non basta; l’associazione deve essere esplicita.',
          'Collega le anagrafiche alla stessa identità di gruppo. Presenze, fascicoli e accordi restano legati alla sede di origine.',
          'Per una variazione apri Storico contratti della persona e inserisci decorrenza, eventuale termine, ore, part-time e condizioni pertinenti.',
          'Chiudi l’intervallo precedente prima di crearne uno che si sovrappone. Motiva le correzioni e verifica il periodo storico.',
          'Per i conteggi economici mensili continua a verificare Accordi e calcoli: un record storico non va interpretato come approvazione automatica di una tariffa.'
      ], 'Una persona ha un riferimento comune di gruppo e uno storico consultabile senza perdere le registrazioni locali.',
      ['Possibile omonimia: interrompi l’associazione finché i riferimenti non sono stati verificati.', 'Date sovrapposte o fine precedente all’inizio: correggi gli intervalli.', 'Le statistiche delle presenze continuano a mostrare le anagrafiche per centro, ove indicato.'])
topic('hrcentrale', 'Documenti HR centrali', 'HR centrale e amministratori',
      'Visionare i documenti amministrativi caricati dalle sedi.', [
          'Accedi con il ruolo HR centrale assegnato dall’amministratore e apri Documenti HR.',
          'Filtra per centro, persona, categoria o testo usando i controlli presenti. Verifica sempre il centro di provenienza.',
          'Apri Visualizza per leggere il PDF o l’immagine nel browser. Il contenuto viene richiesto al server dopo il controllo dei permessi.',
          'Se serve una copia usa Scarica; se serve correggere metadati o fascicolo apri la scheda della persona nel centro.',
          'Dopo un caricamento remoto aggiorna l’elenco. Non serve sincronizzare file o aprire cartelle del PC della sede.'
      ], 'L’ufficio HR consulta un archivio comune con provenienza e autore del caricamento.',
      ['L’account compilatore o lettore non abilita ai documenti riservati: il ruolo va assegnato nominativamente.', 'Se il browser non visualizza un PDF, usa Scarica e un lettore PDF aziendale.'])
topic('accordi', 'Accordi e calcoli del mese', 'Responsabili autorizzati, HR centrale e amministratori secondo i permessi',
      'Confermare le regole economiche per una persona, un centro e un mese.', [
          'Scegli centro e mese, poi Apri accordo sulla persona. Controlla origine dei valori, versione e segnalazioni.',
          'Scegli Turni, Ore oppure Quota fissa e la base Tutto il conteggiabile oppure Conteggiabile meno teorico.',
          'Imposta teorico, tariffe, detrazioni, quota fissa e rettifiche secondo l’accordo effettivo. Consulta il catalogo per ogni parametro.',
          'Seleziona solo le causali non lavorate che l’accordo prevede nel conteggiabile e decidi se includere presenze fuori sede.',
          'Spunta la conferma dopo aver verificato causali e calendario, scrivi una motivazione di almeno 8 caratteri e salva. Può essere richiesta password e 2FA.',
          'Rileggi importo e stato. Senza accordo confermato o con orari mancanti nel modello ore, il risultato può restare non calcolabile.'
      ], 'La modifica riguarda quella persona, quel centro e quel mese, ed è registrata nello storico.',
      ['Importo negativo: resta visibile per la verifica e non è un pagamento automatico.', 'Mese chiuso: accordo consultabile, modifiche bloccate.', 'Tariffa €/turno non equivale a €/ora: controlla prima l’unità di calcolo.'],
      [('[data-agreement]', 'Apri l’accordo individuale del mese.'), ('#ag-model', 'Scegli turni, ore o quota fissa.'), ('#ag-confirmed', 'Conferma soltanto dopo la verifica.'), ('#saveAgreement', 'Salva con una motivazione; il servizio può chiedere la verifica 2FA.')])
topic('riepilogo', 'Riepilogo e chiusura del mese', 'Consultazione secondo ruolo; chiusura e riapertura ai responsabili autorizzati',
      'Controllare i totali e proteggere il mese concluso.', [
          'Scegli centro e mese, poi confronta turni, giorni, ore note, fuori sede, festivi e assenze.',
          'Controlla Da consuntivare e turni senza orari. Torna a Presenze o Da completare per correggere gli elementi mancanti.',
          'Esporta riepilogo CSV, dettaglio CSV o Stampa se il tuo account è autorizzato.',
          'Il responsabile apre Controlli, verifica parametri e calendario, quindi torna qui e preme Chiudi mese.',
          'La chiusura blocca le modifiche. Per una correzione successiva usa Riapri mese, inserisci la motivazione e richiudi dopo la verifica.'
      ], 'Il mese viene marcato Chiuso e le esportazioni ne indicano lo stato.',
      ['Non è presente un processo Inviato/Approvato: questa versione usa Aperto/Chiuso con verifica e riapertura motivata.', 'Chiusura rifiutata per orari mancanti: completa gli orari se il centro li richiede.'],
      [('#exportSummary', 'Scarica il riepilogo, se autorizzato.'), ('#closeMonth', 'Chiudi o riapri il mese selezionato con i permessi necessari.')])
topic('controlli', 'Controlli e storico', 'Tutti in consultazione secondo ruolo; verifica del mese ai responsabili',
      'Leggere le anomalie e dichiarare la verifica dei parametri mensili.', [
          'Scegli centro e mese, poi leggi ogni segnalazione: intervalli tra turni, orari, calendario e registrazioni da verificare.',
          'Confronta la versione dei parametri del mese con quella attuale del centro. Un mese compilato può conservare una versione precedente.',
          'Correggi i dati nella pagina di origine. Ritorna qui e verifica se le segnalazioni si sono aggiornate.',
          'Se autorizzato, spunta Ho verificato parametri e calendario del mese, scrivi una nota utile e premi Salva verifica.',
          'Consulta il registro delle modifiche per autore, data e tipo di operazione. La verifica non chiude il mese: la chiusura è in Riepilogo.'
      ], 'La verifica e le operazioni sono registrate senza modificare automaticamente le presenze.',
      ['Mese chiuso: la verifica non è modificabile finché il mese non viene riaperto.', 'Una segnalazione organizzativa va valutata dal referente; non equivale da sola a una certificazione.'],
      [('#verifiedPeriod', 'Dichiara la verifica del calendario e delle regole.'), ('#periodNote', 'Lascia un riferimento utile al controllo.'), ('#saveVerify', 'Salva la verifica del mese.')])
topic('parametri', 'Parametri del centro: tutte le impostazioni', 'Responsabili e amministratori abilitati; altri ruoli in lettura',
      'Configurare regole del centro sapendo quando entrano in vigore.', [
          'Apri Parametri nel centro corretto. Controlla la versione attuale e quella del mese selezionato.',
          'In Fasce e orari definisci fasce, orari, pause e turni oltre mezzanotte. In Causali definisci lavoro, assenza, riposo e fasce ammesse.',
          'In Calendario e ruoli indica giorni di apertura, festività, qualifiche e sedi esterne. In Permessi e controlli scegli cosa può fare il compilatore.',
          'In Parametri economici imposta i valori iniziali per i nuovi accordi; gli accordi già memorizzati non cambiano. In Carico e stampa configura riferimenti organizzativi e CSV.',
          'Consulta il catalogo qui sotto per nome, effetto ed esempio di ogni impostazione. Premi Salva nuova versione e verifica il messaggio.',
          'Se necessario usa Applica al mese vuoto selezionato. Non usare una modifica di configurazione per riscrivere silenziosamente un mese già compilato.'
      ], 'Le regole sono versionate per mese; i permessi del compilatore si aggiornano subito.',
      ['Una causale non compare: controlla Attiva e Fasce autorizzate.', 'Le nuove tariffe non cambiano un accordo esistente: apri Accordi e calcoli e conferma la variazione mensile.', 'La pausa deve essere coerente con la durata della fascia; controlla Giorno +1 per il notturno.'],
      [('[data-config-tab="fasce"]', 'Definisci le fasce del centro.'), ('[data-config-tab="permessi"]', 'I permessi del compilatore hanno effetto immediato.'), ('#saveConfig', 'Salva una nuova versione di configurazione.'), ('#applyConfig', 'Applica le regole solo a un mese vuoto idoneo.')])
topic('centri', 'Centri e importazione Excel', 'Tutti vedono i centri assegnati; creazione e importazione agli amministratori',
      'Aprire una sede e creare un centro senza mescolare archivi.', [
          'Apri Centri e seleziona la sede; il pulsante porta a parametri o presenze in base ai permessi.',
          'L’amministratore usa Aggiungi centro, indica nome e codice univoco, quindi sceglie valori iniziali o copia la configurazione di una sede esistente.',
          'La copia riguarda la configurazione iniziale: verifica calendario, fasce, causali e ruoli prima di compilare.',
          'Per un modello Excel compatibile usa Importa modello Excel, massimo 12 MB. Leggi l’anteprima con centro, mese, persone e avvisi.',
          'Conferma soltanto dopo il confronto: l’importazione crea un centro separato ed è preceduta da backup; il file originale rimane invariato.'
      ], 'Il centro lavora sul database centrale ed è assegnabile agli account.',
      ['Importare due volte può creare dati separati: usa un solo file autorevole.', 'Un Excel generico non è necessariamente un modello importabile; controlla gli avvisi dell’anteprima.'],
      [('#newCenter', 'Crea un centro con nome, codice e configurazione iniziale.'), ('#importExcel', 'Apri l’anteprima di un modello Excel compatibile.')])
topic('statistiche', 'Statistiche del personale', 'Account autorizzati; contenuti HR solo ai ruoli abilitati',
      'Confrontare periodi e centri leggendo la completezza dei dati.', [
          'Seleziona centro o tutti i centri autorizzati e un intervallo Dal mese / Al mese, fino a 24 mesi.',
          'Filtra per ruolo e, per un singolo centro, per persona. Premi Aggiorna se necessario.',
          'Leggi prima la completezza degli orari: i turni senza orari non producono ore stimate; un mese senza dati resta non disponibile.',
          'Seleziona un mese nel grafico o un centro nella tabella per approfondire. Il dettaglio persona apre il registro.',
          'Esporta Excel quando autorizzato. Il file segue gli stessi filtri e permessi della pagina.'
      ], 'Ottieni confronti con ore note, turni, fasce di assenza e qualità dei dati distinguibili.',
      ['La quota delle assenze registrate non è un tasso contrattuale di assenteismo né un saldo ferie.', 'La situazione HR è attuale e indipendente dai mesi delle presenze.', 'I ruoli mostrati sono quelli attuali dell’anagrafica; i dettagli per sede possono riportare la stessa persona più volte.'],
      [('#statsCenter', 'Seleziona il perimetro autorizzato.'), ('#statsFrom', 'Scegli il primo mese del confronto.'), ('#statsTo', 'Scegli l’ultimo mese.'), ('#statsExcel', 'Esporta gli stessi filtri in Excel.')])
topic('esportazioni', 'Backup ed esportazioni', 'Excel secondo i permessi; gestione backup riservata agli amministratori',
      'Scaricare un prospetto e verificare la continuità dei dati.', [
          'Scegli Prospetto: presenze centro, presenze complessive, statistiche, anagrafiche/fascicoli, onboarding/scadenze oppure accordi.',
          'Per il registro scegli un solo centro, un mese e Pianificato o Consuntivo. Per i prospetti di periodo scegli fino a 24 mesi; i prospetti HR mostrano la situazione attuale.',
          'Premi Scarica Excel. Dati HR, accordi e backup possono richiedere una nuova verifica con password e secondo fattore.',
          'L’amministratore configura una seconda destinazione di backup sul server, conservazione e prova di ripristino. Il percorso deve essere raggiungibile dall’account del servizio.',
          'Crea backup adesso e controlla esito della copia locale e separata. Una destinazione separata sullo stesso disco non protegge dal guasto di quel disco.',
          'Esegui la prova di ripristino sulla copia indicata e controlla data/esito. La prova tecnica va accompagnata periodicamente da un collaudo completo di accesso e consultazione.'
      ], 'Hai un file esportato e copie verificabili, con chiave 2FA originale conservata separatamente.',
      ['Nessun backup separato: verifica percorso, unità montata, spazio e permessi del servizio.', 'Un Excel non contiene gli allegati binari e non sostituisce un backup.', 'I backup contengono dati riservati: proteggi la destinazione con gli accessi aziendali.', 'Per ripristinare sul server ferma il servizio e segui INSTALLAZIONE_WEB.md e il comando after-restore.'],
      [('#exportKind', 'Scegli quale prospetto scaricare.'), ('#exportCenter', 'Definisci la sede o il gruppo autorizzato.'), ('#exportDownload', 'Scarica il file Excel.'), ('#backupNow', 'Crea e verifica una copia del database.')])
topic('paghe', 'Tracciato paghe configurabile', 'HR centrale, amministratori e responsabili autorizzati',
      'Preparare un CSV coerente con il formato richiesto dal consulente.', [
          'Concorda con il consulente nomi delle colonne, matricole, codici causale, formato data, separatore e unità delle quantità.',
          'Apri Paghe nel centro e mese corretti. Configura il tracciato con le opzioni disponibili e associa ogni causale al codice concordato.',
          'Salva la configurazione e avvia la verifica preliminare. Correggi matricole assenti, causali non mappate e orari mancanti prima di esportare.',
          'Controlla anteprima e stato del mese. Le quantità derivano dal consuntivo; un turno senza orari non deve diventare un numero di ore inventato.',
          'Scarica il CSV e fallo verificare al consulente con un mese pilota prima dell’uso operativo. Lo scaricamento non invia automaticamente il file né produce cedolini.'
      ], 'Il consulente riceve un tracciato leggibile e controllato sulla base delle registrazioni salvate.',
      ['Mappatura causali mancante: completa i codici richiesti dal consulente.', 'Quantità o decimali inattesi: verifica unità e formato configurati.', 'Compatibilità con un gestionale specifico: va collaudata con il suo importatore effettivo.'])
topic('utenti', 'Utenti e permessi', 'Solo amministratori',
      'Assegnare accessi personali, sedi e ruolo senza condividere account.', [
          'Apri Utenti e permessi e scegli Nuovo utente. Inserisci nome, nome utente e password iniziale di almeno 12 caratteri.',
          'Scegli il profilo: Compilatore per presenze; Lettore per consultazione; Responsabile per gestione della sede; HR centrale per fascicoli e documenti di gruppo; Amministratore per gestione tecnica e account.',
          'Assegna i centri richiesti dai ruoli di sede. Il ruolo HR centrale opera sui fascicoli di tutte le sedi; l’amministratore ha accesso globale.',
          'Salva e conserva il codice di attivazione mostrato una sola volta, valido 7 giorni. Consegnalo riservatamente alla persona, separatamente dalla password.',
          'Per cessazione disabilita Account attivo. Le modifiche all’account revocano le sue sessioni.',
          'Per telefono perso verifica prima l’identità, poi Ripristina 2FA con motivazione: il vecchio dispositivo, i recuperi e le sessioni vengono revocati.'
      ], 'Ogni persona entra con credenziali proprie e secondo le autorizzazioni previste.',
      ['Un ruolo tecnico non va assegnato solo per consentire lettura documenti: usa HR centrale.', 'La nuova password amministrativa non disabilita il secondo fattore.', 'La creazione dell’account mostra le istruzioni ma non spedisce il codice di attivazione per email.'],
      [('#newUser', 'Crea un account nominativo.'), ('#userRole', 'Scegli il profilo adatto alle attività.'), ('#saveUser', 'Salva e conserva il codice di prima attivazione.')])
topic('sicurezza', 'Sicurezza: password, 2FA e sessioni', 'Ogni utente gestisce il proprio account',
      'Mantenere l’accesso recuperabile e chiudere le sessioni non più necessarie.', [
          'Apri Sicurezza · 2FA dal pulsante in alto e controlla codici di recupero disponibili e attività recenti.',
          'Prima di cambiare telefono premi Cambia dispositivo, collega il nuovo Authenticator e conferma il codice. Conserva i nuovi recuperi.',
          'Rigenera codici sostituisce immediatamente i vecchi: scarica i nuovi e conservali separati dal telefono.',
          'Cambia password richiede quella attuale e una nuova di almeno 12 caratteri ripetuta due volte; tutte le sessioni vengono disconnesse.',
          'Esci dagli altri dispositivi revoca le altre sessioni. Esci nell’intestazione termina quella attuale.'
      ], 'Sai quali strumenti consentono l’accesso e puoi rimuovere quelli non più affidabili.',
      ['Telefono perso: usa password e un recupero monouso; se non disponibile contatta l’amministratore per la verifica d’identità.', 'Password dimenticata: il referente autorizzato esegue il recupero previsto; non esiste una password universale.', 'Conferma di sicurezza: può richiedere nuovamente password e codice per operazioni riservate.'],
      [('#rotateMfa', 'Collega il nuovo telefono prima di dismettere il vecchio.'), ('#newRecovery', 'Genera una nuova serie di codici monouso.'), ('#changePassword', 'Cambia la password personale.'), ('#revokeSessions', 'Chiudi le sessioni degli altri dispositivi.')])
topic('carico', 'Carico per fascia', 'Responsabili e amministratori abilitati',
      'Registrare quantità aggregate di pazienti e leggere i rapporti organizzativi.', [
          'Scegli centro e mese, poi data e fascia della rilevazione.',
          'Inserisci numero di pazienti ordinari e in contumacia. Non inserire nomi né dati identificativi dei pazienti.',
          'Salva conteggio; il mese deve essere aperto. Il personale disponibile viene ricavato dalle presenze e dai ruoli configurati.',
          'Leggi rapporti INF/MED e indici rispetto ai riferimenti del centro. Contumacia e peso configurato incidono sul riferimento infermieristico.',
          'Se un dato è N/D verifica presenze pertinenti e configurazione dei ruoli, senza sostituire N/D con zero.'
      ], 'La tabella offre un riferimento organizzativo per data e fascia, da valutare con i referenti.',
      ['I rapporti non certificano l’adeguatezza clinica o normativa.', 'Una giornata senza conteggio pazienti rimane senza dato.', 'Numeri negativi non sono ammessi.'],
      [('#patDay', 'Scegli la data del conteggio.'), ('#patSlot', 'Seleziona la fascia corretta.'), ('#patOrdinary', 'Inserisci solo un totale aggregato.'), ('#savePatients', 'Salva il conteggio per data e fascia.')])
topic('guida', 'Guida, tutorial e videoguide', 'Tutti gli utenti',
      'Trovare una procedura completa o il significato di un singolo campo.', [
          'Cerca una parola, per esempio part-time, festivo, IBAN o backup: i risultati comprendono pagine e singole impostazioni.',
          'Apri una guida per leggere destinatari, scopo, passi, risultato atteso e problemi frequenti.',
          'Nel catalogo espandi l’impostazione per leggerne effetto ed esempio. Gli esempi sono illustrativi e vanno adattati ai dati reali.',
          'Avvia la videoguida: è un video illustrato locale senza audio, con capitoli, controlli e sottotitoli. Puoi mettere in pausa, tornare indietro e leggere la trascrizione.',
          'Dalla pagina su cui lavori usa Aiuto pagina e Avvia tour. Il tour evidenzia solo i controlli disponibili sullo schermo e non salva o modifica dati.'
      ], 'Ogni pagina e impostazione del catalogo dispone di istruzioni consultabili anche nel manuale incluso nello ZIP.',
      ['Se il tour non trova controlli visibili, apri prima la pagina o la sezione indicata.', 'Le funzioni protette restano soggette ai permessi: la Guida descrive anche azioni riservate ad altri ruoli.'])

topic('strutture', 'Strutture: rubrica e riferimenti del dipendente',
      'HR centrale e amministratori; responsabili nei centri assegnati',
      'Conservare i recapiti della struttura in una scheda condivisa con i fascicoli dei suoi dipendenti.', [
          'Apri Strutture e cerca nome, codice o referente. Sono visibili soltanto i centri che il tuo profilo è autorizzato a gestire.',
          'Premi Apri scheda. Completa ragione sociale, riferimenti fiscali e sede con i dati disponibili: i campi sono facoltativi.',
          'Registra separatamente email generale, email HR, email amministrazione e PEC. Inserisci un solo indirizzo per campo; le liste email usano il recapito scelto esplicitamente.',
          'Indica telefono, referente, direttore e sito web completo di https://. Usa le note per informazioni organizzative utili e aggiornate.',
          'Premi Salva struttura. La versione aumenta e i fascicoli del centro mostrano i nuovi dati senza doverli ricopiare in ogni dipendente.',
          'Nel fascicolo apri Struttura di riferimento per consultarli e Apri rubrica per modificarli. Questo collegamento segue il centro del fascicolo; non trasferisce il dipendente né cambia le presenze.'
      ],
      'La sede e HR centrale consultano gli stessi recapiti della struttura, mantenuti in un unico punto.',
      ['Versione cambiata: riapri la scheda, confronta i dati aggiornati e ripeti soltanto le modifiche ancora necessarie.',
       'Email non valida: inserisci un solo indirizzo senza nomi, spazi o righe aggiuntive. Il controllo del formato non verifica l’esistenza della casella.',
       'Struttura assente: verifica i centri assegnati al tuo account. Nome e codice del centro si gestiscono nelle rispettive anagrafiche.'],
      [('#structureSearch', 'Cerca una struttura tra i centri autorizzati.'),
       ('[data-structure-open]', 'Apri la scheda condivisa della struttura.'),
       ('#structure_hr_email', 'Questo è il recapito HR della struttura, distinto dall’email personale del dipendente.'),
       ('#structureSave', 'Salva i dati condivisi con tutti i fascicoli del centro.')])

topic('comunicazioni', 'Email: modelli, liste e invii',
      'HR centrale e amministratori; configurazione del servizio riservata agli amministratori',
      'Preparare email personalizzate e invii individuali a una lista, controllando i destinatari prima di confermare.', [
          'Apri Comunicazioni. Puoi preparare modelli, liste e bozze anche quando il servizio email è disattivato. Nella demo gli invii sono simulati e non esce alcun messaggio.',
          'Scegli un modello precompilato o creane uno. Compila nome, oggetto e testo; usa soltanto le variabili indicate dal portale, per esempio {{nome}} e {{struttura}}.',
          'Crea una lista: scegli dipendenti oppure contatti delle strutture, poi sedi e filtri pertinenti. Seleziona esplicitamente email aziendale o personale; per le strutture scegli email generale, HR o amministrazione. Aggiungi eventuali indirizzi da escludere.',
          'Nella composizione scegli modello e lista, adatta oggetto e testo, poi genera l’anteprima. Controlla destinatari effettivi, duplicati rimossi, indirizzi mancanti e contenuto personalizzato di ogni messaggio.',
          'Correggi le anomalie e genera nuovamente l’anteprima. Salva la bozza: destinatari e testi vengono conservati così come verificati; le modifiche successive alla rubrica non riscrivono quella bozza.',
          'Quando il servizio aziendale è configurato, apri la bozza e conferma l’invio del lotto indicato. Ogni email ha un solo destinatario. Se rimangono messaggi in attesa, controlla l’esito e avvia esplicitamente il lotto successivo.',
          'Consulta lo storico per ogni destinatario. Accettato significa preso in carico dal server SMTP, non ricevuto o letto. Per le campagne manuali puoi ritentare gli invii falliti; i promemoria automatici non si ritentano da questa pagina. Per un esito incerto verifica prima col tecnico per evitare un doppio messaggio.'
      ],
      'Lo storico conserva una copia dei messaggi preparati e l’esito dei tentativi. I promemoria periodici si configurano separatamente nella pagina Promemoria.',
      ['Invio disattivato: chiedi al tecnico di configurare il servizio di posta; nel frattempo conserva le bozze.',
       'Anteprima non più valida: rigenerala dopo aver modificato modello, lista o dati dei destinatari.',
       'Variabile sconosciuta o dato mancante: correggi modello o rubrica e ricontrolla il testo personalizzato.',
       'Limite di invio raggiunto: attendi prima di avviare il lotto successivo. Un errore di recapito non va risolto inviando di nuovo agli indirizzi già accettati.',
       'Invio rimasto in corso dopo un’interruzione: trascorsi 15 minuti senza aggiornamenti, usa Riconcilia invio interrotto. I tentativi sospesi diventano incerti; il comando non invia email. Verifica gli esiti con il tecnico prima di preparare altri messaggi.'],
      [('[data-comm-section="templates"]', 'Prepara e salva i modelli con le sole variabili ammesse.'),
       ('[data-comm-section="lists"]', 'Definisci destinatari, filtri e indirizzi da escludere.'),
       ('[data-comm-section="compose"]', 'Componi una comunicazione e consulta le bozze e gli invii.'),
       ('#commPreview', 'Ricalcola i destinatari e leggi le email personalizzate senza inviarle.'),
       ('#commDraftCreate', 'Conserva la versione verificata dei destinatari e dei testi.'),
       ('#commCampaignSelect', 'Apri una bozza o controlla gli esiti dei singoli destinatari.'),
       ('[data-comm-section="settings"]', 'Solo l’amministratore configura e abilita il servizio di posta.'),
       ('#commSendOpen', 'Rileggi la bozza prima di confermare l’invio reale del lotto.')])

settings('strutture', 'Identità della struttura', '''structure.legal_name|Ragione sociale|Identifica la società o l’ente di riferimento della struttura; non cambia il nome del centro nelle presenze.|NefroCenter Demo S.r.l.
structure.vat_number|Partita IVA|Conserva il riferimento fiscale della struttura; non certifica la posizione fiscale.|Riporta il dato aziendale verificato.
structure.tax_code|Codice fiscale della struttura|Conserva il codice fiscale dell’ente, se diverso o necessario.|Inserisci il codice comunicato dall’amministrazione.''')
settings('strutture', 'Sede e recapiti', '''structure.address|Indirizzo della struttura|Indirizzo della sede di riferimento condiviso con i fascicoli del centro.|Via Esempio 10.
structure.city|Comune della struttura|Comune della sede, distinto dalla residenza del dipendente.|Napoli.
structure.postal_code|CAP della struttura|Codice postale della sede.|80100, solo come esempio.
structure.province|Provincia della struttura|Provincia della sede.|NA.
structure.phone|Telefono della struttura|Recapito telefonico organizzativo; il gestionale non effettua chiamate.|Numero del centralino.
structure.email|Email generale della struttura|Casella ordinaria usata quando la lista seleziona il contatto generale.|sede@example.invalid.
structure.hr_email|Email ufficio HR della struttura|Casella del referente HR disponibile nei fascicoli e nelle liste che scelgono il recapito HR.|hr@example.invalid.
structure.admin_email|Email amministrazione della struttura|Casella amministrativa, distinta da HR e dall’indirizzo personale del dipendente.|amministrazione@example.invalid.
structure.pec|PEC della struttura|Conserva il recapito PEC come riferimento. Il modulo email ordinario non effettua invii PEC certificati.|struttura@pec.example.invalid.
structure.website|Sito web della struttura|Indirizzo completo con http:// o https://; non è un collegamento automatico a un servizio esterno.|https://www.example.invalid.''')
settings('strutture', 'Referenti e salvataggio', '''structure.contact_name|Referente della struttura|Nome del contatto organizzativo della sede.|Referente Sede Demo.
structure.director|Direttore della struttura|Nome del responsabile della direzione della struttura.|Direzione Demo.
structure.notes|Note organizzative|Informazioni utili ai colleghi autorizzati; massimo 2000 caratteri.|Orari per contattare l’amministrazione.
structure.save|Salva struttura|Aggiorna la versione della scheda e rende i dati disponibili nei fascicoli del centro; non cambia le assegnazioni.|Correggi il telefono una sola volta per tutti i fascicoli.''')
settings('comunicazioni', 'Modelli', '''communication.template.name|Nome modello|Etichetta interna per ritrovare il testo precompilato; non è l’oggetto dell’email.|Richiesta documenti mancanti.
communication.template.subject|Oggetto modello|Titolo dell’email, personalizzato con le variabili ammesse. Non inserire righe aggiuntive.|Promemoria per {{nome}}.
communication.template.body|Testo modello|Corpo dell’email in testo semplice; usa solo le variabili elencate dal portale.|Gentile {{nome}}, contatta il referente di {{struttura}}.
communication.variables|Variabili del modello|Sostituiscono i segnaposto con dati del destinatario o della struttura. Anteprima e controlli segnalano variabili o dati non utilizzabili.|{{struttura}} mostra il nome del centro.''')
settings('comunicazioni', 'Liste destinatari', '''communication.list.name|Nome lista|Etichetta interna della selezione di destinatari.|Personale Sede Demo.
communication.list.recipient_type|Tipo destinatari|Sceglie tra fascicoli dei dipendenti e contatti delle strutture.|Strutture per una comunicazione ai referenti HR.
communication.list.cids|Strutture della lista|Limita i destinatari ai centri selezionati. Nessuna selezione include tutti i centri autorizzati: controlla sempre il totale nell’anteprima.|Seleziona soltanto le sedi coinvolte.
communication.list.roles|Ruoli del personale|Filtra i dipendenti secondo il ruolo registrato; nessuna selezione comprende tutti i ruoli. Non modifica le autorizzazioni al portale.|INF per i fascicoli con ruolo infermieristico.
communication.list.stages|Stati del rapporto|Filtra i fascicoli secondo lo stato selezionato. Nessuna selezione comprende tutti gli stati, anche i cessati.|In ingresso per una comunicazione di benvenuto.
communication.list.email_field|Email aziendale o personale|Sceglie esplicitamente il campo del fascicolo. Un indirizzo assente viene segnalato, senza sostituzione nascosta con un altro recapito.|Email aziendale per le comunicazioni interne.
communication.list.structure_field|Recapito della struttura|Sceglie email generale, HR o amministrazione per una lista di strutture.|Email ufficio HR.
communication.list.exclude_emails|Indirizzi esclusi|Esclude dalla selezione gli indirizzi indicati. I duplicati fra destinatari vengono eliminati nell’anteprima.|Escludi una casella che deve ricevere una comunicazione separata.''')
settings('comunicazioni', 'Composizione e storico', '''communication.preview|Genera anteprima|Ricalcola destinatari, anomalie e messaggi personalizzati sui dati aggiornati, senza inviare email.|Controlla tutti i destinatari prima di creare la bozza.
communication.draft|Salva bozza|Conserva una copia dei destinatari e dei testi verificati. La bozza non si aggiorna quando cambia la lista o la rubrica.|Crea una nuova bozza dopo una correzione dei recapiti.
communication.send|Conferma invio lotto|Avvia esplicitamente un lotto di email individuali; può richiedere conferma di sicurezza. Non iscrive un’attività automatica.|Conferma soltanto dopo aver riletto conteggio e testi.
communication.retry_failed|Ritenta falliti|Riprova soltanto i destinatari con errore; non reinvia quelli già accettati e non risolve gli esiti incerti.|Correggi prima la causa indicata dal servizio.
communication.status|Stato invio|Distingue messaggi in attesa, in lavorazione, accettati dal server, falliti o con esito incerto; l’accettazione SMTP non conferma lettura o consegna.|Accettato: il server ha preso in carico il messaggio.''')
settings('comunicazioni', 'Configurazione email — amministratore', '''communication.smtp.enabled|Abilita servizio email|Consente gli invii reali solo dopo configurazione e verifica del servizio. Inizialmente è disattivato.|Lascia disattivato finché il fornitore non è definito.
communication.smtp.host|Server SMTP|Nome del server fornito dal servizio aziendale; non usare un indirizzo ipotizzato.|Il tecnico inserisce il server comunicato dal fornitore.
communication.smtp.port|Porta SMTP|Porta abbinata alla modalità TLS richiesta dal fornitore.|Usa la porta indicata nella documentazione del servizio.
communication.smtp.security|Modalità TLS|Sceglie TLS diretto oppure STARTTLS con verifica del certificato. L’invio in chiaro non è previsto.|SSL/TLS o STARTTLS secondo il fornitore.
communication.smtp.username|Nome utente SMTP|Account autorizzato a spedire dal servizio aziendale.|Casella tecnica autorizzata.
communication.smtp.password|Password del servizio sul server|Il tecnico imposta PRESENZE_SMTP_PASSWORD nell’ambiente del servizio; la password non si salva nei modelli o nella rubrica.|Non incollare credenziali nel testo di una comunicazione.
communication.smtp.from_email|Email mittente|Indirizzo da cui partono i messaggi; deve essere autorizzato dal servizio di posta.|hr@example.invalid come esempio fittizio.
communication.smtp.from_name|Nome mittente|Nome leggibile mostrato accanto all’indirizzo del mittente.|Ufficio HR.
communication.smtp.reply_to|Rispondi a|Casella a cui indirizzare le risposte quando diversa dal mittente.|ufficio.personale@example.invalid.
communication.smtp.batch_size|Dimensione lotto|Da 1 a 20 messaggi elaborati con una conferma; i successivi richiedono un nuovo avvio.|Usa lotti piccoli nella prova iniziale; valore iniziale 20.
communication.smtp.max_per_hour|Limite orario|Da 1 a 2000 tentativi nell’ultima ora; rispetta anche i limiti del servizio aziendale, che possono essere più bassi.|Concorda il valore con il tecnico; valore iniziale 100.''')

settings('parametri', 'Fasce e orari', '''slots.id|Codice fascia|Identifica la fascia nel registro e nei vincoli delle causali. Scegli un codice distinto e stabile.|M per Mattina; N per Notte.
slots.label|Descrizione fascia|Mostra il nome leggibile della fascia nei selettori e nella legenda.|Mattina.
slots.start|Ingresso della fascia|Propone l’inizio standard per le nuove registrazioni che usano questa fascia.|08:00.
slots.end|Uscita della fascia|Propone l’uscita standard; per un orario oltre mezzanotte serve Giorno +1.|14:00, oppure 06:00 con ingresso 22:00 e Giorno +1.
slots.pause|Pausa in minuti|Sottrae i minuti di pausa dalla durata del lavoro; deve essere coerente con la fascia.|30 trasforma 08:00–14:00 in 5 ore e 30 minuti.
slots.overnight|Giorno +1|Indica che l’uscita appartiene al giorno successivo all’ingresso.|Attivo per 22:00–06:00.
slots.color|Colore fascia|Aiuta a riconoscere visivamente la fascia; non modifica i conteggi.|Blu per Mattina.
slots.active|Fascia attiva|Rende la fascia disponibile alle nuove registrazioni; lo storico resta consultabile.|Disattiva una fascia che non si usa più dopo aver verificato le causali.
slots.add|Aggiungi fascia|Crea una fascia e una causale lavoro iniziale associata; completa entrambi i codici prima di salvare.|Crea SERA, poi verifica orario e causale.
slots.remove|Rimuovi fascia|Rimuove la riga dalla nuova configurazione; preferisci disattivare quando il codice è già stato usato.|Rimuovi una riga appena creata per errore.''')
settings('parametri', 'Causali', '''codes.id|Codice causale|Identifica il tipo di registrazione nelle celle e nelle esportazioni.|FER per ferie.
codes.label|Descrizione causale|Spiega il significato del codice in legenda e selezione.|Ferie autorizzate.
codes.kind|Tipo causale|Distingue Lavoro, Assenza e Riposo; determina a quali conteggi contribuisce la registrazione.|FER → Assenza; RIP → Riposo.
codes.allowed_slots|Fasce autorizzate|Limita l’uso della causale ai codici fascia elencati, separati da virgole; vuoto significa tutte.|M,P consente mattina e pomeriggio.
codes.credit_minutes|Credito minuti dell’assenza|Attribuisce un credito separato dalle ore effettivamente lavorate; entra nel modello ore solo quando l’accordo include quella causale.|360 per un credito di sei ore, se previsto dall’accordo.
codes.color|Colore causale|Colora il riferimento visivo della causale senza modificarne natura e conteggio.|Arancione per FER.
codes.active|Causale attiva|Consente di scegliere la causale per nuove registrazioni. Le registrazioni storiche non scompaiono.|Disattiva una causale sostituita dal nuovo modello.
codes.add|Aggiungi causale|Aggiunge una riga da completare con codice, descrizione, tipo e fasce ammesse.|Aggiungi FOR per formazione lavorativa secondo le regole aziendali.
codes.remove|Rimuovi causale|Toglie la definizione dalla nuova versione; valuta la disattivazione per codici usati nello storico.|Elimina soltanto una causale creata per errore.''')
settings('parametri', 'Calendario e ruoli', '''weekdays|Giorni della settimana|Definisce i giorni del calendario lavorativo teorico del centro.|Lunedì–sabato, domenica esclusa.
holidays|Festività|Elenca una data AAAA-MM-GG per riga; incide sul calendario autorizzato del centro.|2026-12-25.
roles|Ruoli|Definisce le qualifiche selezionabili nelle anagrafiche del centro; una voce per riga.|Infermiere, Medico, Amministrativo.
sites|Sedi esterne autorizzate|Definisce le destinazioni selezionabili per il lavoro fuori sede.|Centro A; Centro B su righe distinte.
note|Note e accordi del centro|Conserva una spiegazione amministrativa della configurazione; non è una formula di calcolo.|Calendario validato il 18/10/2026 dal responsabile.''')
settings('parametri', 'Permessi e controlli', '''operator_edit_times|Può inserire orari effettivi e pause|Abilita il compilatore a correggere ingresso, uscita e pausa; il permesso cambia subito.|Attivalo se la sede rileva gli orari effettivi.
operator_choose_site|Può scegliere una sede esterna autorizzata|Permette al compilatore di selezionare una delle sedi configurate.|Attivalo per chi registra sostituzioni fra centri.
operator_mark_holiday|Può classificare manualmente un festivo|Permette la classificazione manuale del festivo nelle registrazioni, secondo la verifica aziendale.|Lascialo disattivato se la classificazione è riservata al responsabile.
operator_delete|Può eliminare una registrazione|Consente al compilatore la rimozione di una cella registrata, con controllo dei permessi sul server.|Attivalo per correggere duplicati operativi.
operator_export|Può esportare i riepiloghi|Abilita le esportazioni presenze consentite al compilatore; non concede accesso ai fascicoli HR.|Attivalo per inviare il riepilogo autorizzato della sede.
operator_planned|Può compilare la pianificazione|Consente la scrittura nel registro Pianificato.|Attivalo per l’operatore che prepara i turni.
min_rest_hours|Intervallo minimo tra turni, ore|Imposta la soglia di segnalazione organizzativa per l’intervallo tra turni, fra 0 e 48 ore.|11 segnala intervalli inferiori a undici ore.
require_times_on_close|Richiedi orari completi prima della chiusura|Blocca la chiusura quando mancano gli orari necessari dei turni lavorativi.|Attivo richiede di completare 08:00–14:00 prima della chiusura.''')
settings('parametri', 'Economia, carico e stampa', '''weekday_rate|Tariffa feriale iniziale|Propone la tariffa feriale per i nuovi accordi da confermare; non riscrive gli accordi salvati.|20,00 da verificare rispetto a €/ora o €/turno.
holiday_rate|Tariffa festiva iniziale|Propone il valore festivo dei nuovi accordi.|30,00 secondo l’unità e l’accordo.
fixed_deduction|Detrazione fissa iniziale|Propone una sottrazione monetaria nei nuovi accordi, da verificare individualmente.|50,00 se previsto dall’accordo.
ccnl_rate|Rettifica festivo già riconosciuto|Memorizza il riferimento del centro; le rettifiche dei nuovi accordi partono da zero e vanno impostate individualmente.|Verifica e inserisci nell’accordo persona/mese una rettifica di 10,00 quando dovuta.
pay_mode|Base del conteggio iniziale|Propone Tutto il conteggiabile oppure Totale meno teorico ai nuovi accordi.|Totale 24 e teorico 20 → base extra 4 prima delle altre componenti.
nurse_roles|Ruoli infermieristici|Identifica quali ruoli delle presenze entrano nel denominatore infermieristico del carico.|Infermiere, una voce esatta per riga.
doctor_roles|Ruoli medici|Identifica i ruoli che entrano nel denominatore medico del carico.|Medico.
nurse_reference|Riferimento pazienti/infermiere|Valore organizzativo positivo usato come confronto per l’indice INF.|4 significa confronto con quattro pazienti per infermiere, da validare.
doctor_reference|Riferimento pazienti/medico|Valore organizzativo positivo per l’indice MED.|12 come riferimento aziendale esemplificativo.
isolation_weight|Peso contumacia, infermieri|Pesa i pazienti in contumacia nel rapporto infermieristico; non certifica fabbisogni clinici.|1,5 attribuisce peso maggiore di un paziente ordinario.
csv_separator|Separatore CSV|Sceglie punto e virgola, virgola o tabulazione per i CSV gestiti da questo parametro.|Punto e virgola per un importatore che lo richiede.
saveConfig|Salva nuova versione|Registra la configurazione del centro; i mesi compilati conservano le regole già associate.|Modifica a ottobre senza riscrivere settembre.
applyConfig|Applica al mese vuoto selezionato|Associa la configurazione recente a un mese vuoto quando consentito dal servizio.|Prepara novembre prima della prima registrazione.''')
settings('accordi', 'Accordo individuale per centro e mese', '''model|Unità di calcolo|Sceglie turni/fasce, ore effettive e crediti oppure quota fissa; cambia il significato delle tariffe.|Ore: 6 ore × tariffa oraria.
basis|Base di calcolo|Tutto il conteggiabile usa tutte le unità; meno teorico sottrae il teorico individuale.|24 turni meno teorico 20 = 4 prima della ripartizione festivi.
theoretical_mode|Teorico individuale|Da calendario usa i giorni del centro; Valore individuale usa il numero inserito per questo mese.|Manuale per un ingresso a metà mese.
theoretical_units|Teorico individuale, turni oppure ore|Numero usato quando il teorico è manuale; l’unità segue il modello.|80 nel modello Ore significa 80 ore.
hours_per_day|Ore teoriche per giorno|Nel modello Ore converte i giorni teorici del calendario in ore.|6 ore × 20 giorni = 120 ore teoriche.
weekday_rate|Tariffa feriale dell’accordo|Valore monetario per unità feriale; l’unità è turno o ora secondo il modello.|15 €/ora nel modello Ore.
holiday_rate|Tariffa festiva dell’accordo|Valore monetario per unità festiva riconosciuta.|20 €/ora per le ore festive previste.
fixed_deduction|Detrazione fissa|Importo monetario sottratto dal risultato mensile.|−50,00 come effetto di una detrazione impostata a 50.
fixed_amount|Quota fissa / integrazione|Importo aggiunto alle altre componenti, oppure base del modello Quota fissa.|300,00 di integrazione confermata.
adjustment|Rettifica positiva o negativa|Correzione monetaria esplicita con segno, motivata nello storico.|−25,00 rettifica in diminuzione.
ccnl_count|Festivi già riconosciuti, numero|Numero intero moltiplicato per la rettifica unitaria da sottrarre.|2 festivi già riconosciuti.
ccnl_rate|Rettifica per festivo già riconosciuto|Valore unitario sottratto per ciascun festivo già riconosciuto.|2 × 10,00 = 20,00 sottratti.
counted_absences|Causali non lavorate nel conteggiabile|Include soltanto le causali selezionate; nel modello Ore usa il credito minuti configurato.|FER con credito 360 contribuisce sei ore se selezionata.
include_external|Includi le presenze fuori sede|Include nel conteggiabile dell’accordo le presenze esterne quando previsto.|Disattivo se la liquidazione spetta all’altra sede.
confirmed|Conferma accordo, causali e calendario|Rende l’accordo confermato ai fini del calcolo, se i dati sono sufficienti.|Spunta solo dopo aver confrontato il mese con l’accordo firmato.
reason|Motivazione della modifica|Testo di almeno 8 caratteri conservato per comprendere la variazione.|Accordo ottobre verificato con amministrazione.''')

HR_ROWS = '''first_name|Nome|Nome anagrafico distinto dal cognome; aiuta a identificare la persona.|Anna.
last_name|Cognome|Cognome anagrafico; insieme al nome può proporre il nome completo nel registro.|Esempio.
tax_code|Codice fiscale|Identificativo normalizzato in maiuscolo; il formato viene controllato e i duplicati nel centro segnalati.|Trascrivi il codice dal documento, senza inventarlo.
birth_date|Data di nascita|Data anagrafica che deve precedere oggi.|1985-06-12.
birth_place|Luogo di nascita|Comune o località di nascita riportati sul documento.|Napoli.
nationality|Cittadinanza|Cittadinanza dichiarata e verificata amministrativamente.|Italiana.
address|Indirizzo di residenza|Via, numero civico e dettagli della residenza.|Via Esempio 10.
postal_code|CAP|Codice postale della residenza, conservato come testo.|80100.
city|Comune|Comune di residenza.|Napoli.
province|Provincia|Provincia della residenza.|NA.
country|Paese|Stato della residenza.|Italia.
domicile|Domicilio, se diverso|Indirizzo alternativo quando rilevante per il rapporto.|Via Esempio 20, Pozzuoli.
email|Email|Recapito personale; viene controllata la struttura, senza inviare messaggi.|persona@example.org.
phone|Telefono|Recapito telefonico della persona.|+39 seguito dal numero verificato.
emergency_name|Contatto di emergenza, facoltativo|Riferimento da usare secondo la procedura aziendale, se necessario.|Nome e relazione del contatto indicato.
emergency_phone|Telefono di emergenza, facoltativo|Numero del contatto di emergenza.|Numero fornito e verificato dalla persona.
employer|Società datrice di lavoro|Ragione sociale della società titolare del rapporto.|Società Esempio Srl.
department|Reparto / servizio|Unità organizzativa; è usata anche nella ricerca dei fascicoli.|Servizio dialisi.
manager|Responsabile diretto|Referente organizzativo della persona.|Nome del responsabile.
contract_type|Tipologia di contratto|Descrive il rapporto attuale e compare nel collegamento alle presenze.|Tempo indeterminato.
ccnl|CCNL applicato|Riferimento contrattuale amministrativo; non carica automaticamente tabelle normative.|Denominazione completa concordata con il consulente.
level|Livello di inquadramento|Livello riconosciuto nel rapporto, come testo.|Livello riportato nel contratto.
qualification|Mansione / qualifica|Mansione contrattuale, distinta dal ruolo selezionato nelle presenze.|Infermiere professionale.
start_date|Data di ingresso|Data che, al primo salvataggio, genera le scadenze relative dell’onboarding.|2026-11-02.
end_date|Scadenza contratto|Termine eventuale del rapporto e fonte di scadenza; non può precedere l’ingresso.|2027-10-31, oppure vuoto se non previsto.
probation_end|Fine periodo di prova|Data amministrativa di verifica, non anteriore all’ingresso.|2027-01-31.
weekly_hours|Ore settimanali|Informazione contrattuale numerica maggiore di zero e fino a 168; non sostituisce gli accordi mensili.|36.
part_time_percent|Percentuale part-time|Percentuale contrattuale maggiore di zero e fino a 100.|50 per metà tempo; non digitare il simbolo %.
iban|IBAN|Coordinata di pagamento, normalizzata e verificata nel formato e nel controllo numerico.|Copia l’IBAN reale validato dall’ufficio; il software non effettua bonifici.
payroll_contact|Referente paghe|Persona o ufficio cui riferirsi per il rapporto.|Studio paghe / referente amministrativo.
professional_register|Ordine / albo professionale|Organismo professionale pertinente alla mansione.|Ordine professionale e provincia.
register_number|Numero di iscrizione|Numero dell’iscrizione all’albo dichiarato.|Numero riportato sull’attestazione.
registration_expiry|Scadenza abilitazione, se prevista|Data di verifica o scadenza pertinente che alimenta le scadenze HR.|2027-06-30 solo se applicabile.
work_permit_expiry|Scadenza titolo di soggiorno/lavoro|Termine da registrare soltanto quando pertinente al rapporto.|2027-05-31.
next_review|Prossima verifica amministrativa|Promemoria datato per una verifica HR successiva.|2027-01-15.
notes|Note amministrative|Testo amministrativo fino a 2000 caratteri; non è spazio per diagnosi o password.|Attestato ricevuto, verifica in programma.
birth_province|Provincia di nascita|Provincia relativa al luogo di nascita.|NA.
identity_type|Tipo documento di identità|Specifica il documento usato per l’identificazione.|Carta d’identità.
identity_number|Numero documento|Riferimento del documento identificativo.|Numero letto sul documento.
identity_issuer|Ente di rilascio|Autorità che ha emesso il documento.|Comune di esempio.
identity_issued_date|Data di rilascio|Data iniziale di validità documentale.|2022-05-10.
identity_expiry|Scadenza documento|Alimenta le scadenze HR; non può precedere il rilascio.|2032-05-10.
pec|PEC, se pertinente|Indirizzo PEC registrato come recapito, senza invio automatico.|persona@pec.example.org.
company_email|Email aziendale|Recapito lavorativo distinto dall’email personale.|nome.cognome@example.org.
vat_number|Partita IVA, se pertinente|Riferimento fiscale quando richiesto dalla natura del rapporto.|Partita IVA comunicata dal professionista.
payment_method|Modalità di pagamento|Descrive il metodo amministrativo concordato.|Bonifico bancario.
account_holder|Intestatario del conto|Intestazione da confrontare con la coordinata bancaria.|Nome e cognome dell’intestatario.
bank_name|Banca|Istituto di riferimento del pagamento.|Banca indicata nella documentazione.
contract_number|Riferimento contratto|Identificativo che collega il fascicolo al documento del rapporto.|CTR-2026-015.
cost_center|Centro di costo|Codice amministrativo per la classificazione economica.|CC-DIALISI-01.
workplace|Sede di lavoro contrattuale|Luogo contrattuale; non sostituisce la sede della singola presenza.|Centro Esempio.
badge_number|Numero badge|Identificativo del badge aziendale; non attiva timbrature automatiche.|B0042.
tutor|Tutor di inserimento|Referente dell’affiancamento iniziale.|Nome del tutor.'''
_hr_group={
    'anagrafica': {'first_name','last_name','tax_code','birth_date','birth_place','nationality','birth_province','identity_type','identity_number','identity_issuer','identity_issued_date','identity_expiry'},
    'recapiti': {'address','postal_code','city','province','country','domicile','email','phone','emergency_name','emergency_phone','pec','company_email'},
    'contratto': {'employer','department','manager','contract_type','ccnl','level','qualification','start_date','end_date','probation_end','weekly_hours','part_time_percent','contract_number','cost_center','workplace','badge_number','tutor'},
    'amministrazione': {'iban','payroll_contact','vat_number','payment_method','account_holder','bank_name'},
}
for row in HR_ROWS.splitlines():
    key = row.split('|')[0]
    group = next((k for k, v in _hr_group.items() if key in v), 'qualifiche')
    settings(group, 'Campi standard HR', row)
settings('anagrafica', 'Identità nel registro', '''display_name|Nome completo nel registro|Nome visualizzato nelle presenze; obbligatorio, proposto da nome e cognome quando possibile.|Anna Esempio.
registration|Matricola|Codice della persona nel centro, univoco all’interno della sede e necessario nei tracciati che lo richiedono.|P0017.
role|Ruolo nelle presenze|Qualifica scelta tra quelle del centro; entra nei filtri e nei conteggi di carico pertinenti.|Infermiere.
stage|Stato del rapporto|In ingresso, In servizio o Cessato: descrive la fase del rapporto e filtra l’elenco HR.|In ingresso prima del primo giorno.
active|Abilitato alla compilazione delle presenze|Rende la persona disponibile nelle nuove compilazioni; le registrazioni storiche restano visibili.|Disattivato dopo la cessazione verificata.''')
settings('onboarding', 'Aggiorna attività', '''task.status|Stato attività|Da fare, In corso, Completata o Non applicabile; gli ultimi due chiudono l’attività nel progresso.|In corso durante la raccolta dei documenti.
task.due|Scadenza attività|Data della singola attività, modificabile senza alterare il modello.|2026-11-01 per un ingresso il 2 novembre.
task.owner|Responsabile attività|Referente dell’adempimento, indicato come testo; non invia notifiche.|Ufficio HR.
task.note|Nota / motivo di non applicabilità|Registra evidenze o motivazione obbligatoria per Non applicabile.|Non richiesto per questa mansione, verificato con il referente.''')
settings('modellohr', 'Modello del centro', '''template.phase|Fase dell’attività|Raggruppa le attività del modello nel fascicolo.|Prima dell’ingresso.
template.label|Descrizione attività|Descrive in modo operativo ciò che occorre verificare.|Ricevere copia del contratto firmato.
template.owner|Responsabile predefinito|Propone il referente nei nuovi fascicoli.|Amministrazione.
template.offset|Giorni dall’ingresso|Intero da −365 a 730: genera la prima scadenza rispetto alla data d’ingresso.|−7: una settimana prima; 0: primo giorno; 30: dopo trenta giorni.
custom.label|Etichetta campo personalizzato|Nome visibile del campo, fino a 100 caratteri.|Codice dotazione.
custom.type|Tipo campo personalizzato|Testo, Data, Numero o Sì/No determina il controllo del valore.|Data per scadenza formazione interna.
custom.required|Campo richiesto|Segnala l’incompletezza del fascicolo senza impedirne il salvataggio in bozza.|Attivo per un dato che l’ufficio deve ricevere.
custom.remove|Rimuovi definizione campo|Ritira il campo dal modello attivo senza cancellare valori storici già salvati.|Rimuovi una vecchia classificazione non più utilizzata.''')
settings('documenti', 'Allegati', '''document.file|Documento|PDF, PNG o JPEG reale, massimo 6 MiB; il file si conserva nel database centrale.|Contratto_firmato.pdf.
document.category|Categoria|Classifica il documento per ricerca e consultazione HR.|Contratto, Formazione o Documento di identità.
document.expiry|Scadenza del documento|Data facoltativa che alimenta gli elenchi delle scadenze.|2027-06-30 per un titolo che scade.
document.reason|Motivazione rimozione|Spiega perché un allegato viene rimosso dal fascicolo attivo; i backup precedenti possono conservarlo.|Scansione errata sostituita con versione leggibile.''')
settings('utenti', 'Account', '''user.name|Nome dell’utente|Nome leggibile nelle operazioni e nella gestione degli account.|Referente Sede A.
user.username|Nome utente|Identificativo personale di accesso; distinto dal nome del dipendente.|m.rossi.
user.role|Profilo|Definisce azioni e dati accessibili; assegnare HR centrale per consultare fascicoli di tutte le sedi senza gestione degli account.|Compilatore per inserimento presenze.
user.password|Password iniziale / nuova password|Per un nuovo account almeno 12 caratteri; in modifica il campo vuoto conserva la password.|Una frase personale robusta, fornita con canale riservato.
user.centers|Centri assegnati|Limita i ruoli di sede ai centri selezionati; amministratore e HR centrale hanno il perimetro globale previsto dal loro ruolo.|Solo Centro A per il suo compilatore.
user.active|Account attivo|Abilita l’accesso; disattivarlo revoca le sessioni.|Disattivo quando termina l’incarico.
user.reset_reason|Motivo del ripristino 2FA|Registra il riferimento della verifica di identità prima di generare una nuova attivazione.|Telefono sostituito, identità verificata dal referente.''')
settings('sicurezza', 'Accesso personale', '''security.current_password|Password attuale|Conferma l’identità nel cambio password e nelle operazioni protette.|Inserisci la password personale attuale.
security.new_password|Nuova password|Password personale di almeno 12 caratteri, da ripetere identica.|Usa una frase unica per questo portale.
security.otp|Codice Authenticator|Codice TOTP a sei cifre generato dall’app; dipende dall’orologio del dispositivo.|Usa il codice corrente prima della scadenza.
security.recovery|Codice di recupero|Alternativa monouso al TOTP quando selezioni l’opzione corrispondente.|Usa uno dei codici conservati separatamente dal telefono.
security.rotate|Cambia dispositivo|Collega un nuovo Authenticator con conferma del codice e nuovi recuperi.|Effettua il passaggio prima di dismettere il vecchio telefono.
security.regenerate|Rigenera codici|Revoca i vecchi codici e genera una nuova serie visibile una volta sola.|Scarica e custodisci subito la nuova serie.
security.sessions|Esci dagli altri dispositivi|Revoca le sessioni diverse da quella corrente.|Chiudi l’accesso lasciato su una postazione condivisa.''')
settings('centri', 'Creazione e interfaccia', '''center.name|Nome struttura|Etichetta del centro mostrata nelle pagine e nei report.|Centro Esempio.
center.code|Codice centro|Identificativo amministrativo distinto del centro.|ESEMPIO01.
center.copy_from|Configurazione iniziale|Copia regole iniziali da un centro esistente oppure usa valori da verificare.|Copia Centro A, poi adatta le festività locali.
interface.style|Stile interfaccia|Cambia la presentazione grafica sul browser; non modifica presenze, permessi o calcoli.|Attuale, Editoriale, Essenziale o Spazio di lavoro.''')
settings('presenze', 'Registrazione e filtri', '''entry.layer|Consuntivo / Pianificato|Separa quanto svolto da quanto previsto; il pianificato non genera ore lavorate effettive.|Pianifica il 5 novembre, poi registra il consuntivo dopo il turno.
entry.code|Causale della cella|Determina lavoro, assenza o riposo per persona, giorno e fascia.|FER per la fascia di ferie autorizzata.
entry.start|Ingresso effettivo|Orario di inizio realmente registrato quando il ruolo può modificarlo.|08:05.
entry.end|Uscita effettiva|Orario di fine; con passaggio al giorno successivo consente il notturno.|14:05 oppure 06:00 del giorno seguente.
entry.pause|Pausa effettiva|Minuti da sottrarre alla durata della presenza lavorativa.|30.
entry.site|Sede di lavoro|Centro di effettuazione del turno; una sede diversa conta come fuori sede.|Centro B per una sostituzione.
entry.holiday|Festivo riconosciuto|Classifica il turno come festivo quando il calendario o il permesso lo consentono.|Flag verificato per una festività autorizzata.
entry.note|Nota della registrazione|Spiega un’eccezione del turno senza inserire informazioni sanitarie non necessarie.|Sostituzione concordata con il responsabile.
gridWindow|Mese completo / 7 giorni|Cambia soltanto la porzione di calendario visibile; i totali restano mensili.|7 giorni per lavorare dal telefono.
searchPeople|Ricerca persona e filtro ruolo|Restringe l’elenco mostrato, senza cancellare registrazioni.|Cerca Anna oppure seleziona Infermiere.''')
settings('controlli', 'Verifica mensile', '''period.verified|Ho verificato parametri e calendario|Registra la verifica del mese; non costituisce un flusso di invio/approvazione e non chiude il registro.|Spunta dopo aver confrontato festività e fasce.
period.note|Nota del mese|Conserva il riferimento del controllo organizzativo effettuato.|Calendario verificato con la sede il 30 novembre.
period.reopen_reason|Motivo riapertura|Spiega la modifica a un mese precedentemente chiuso.|Correzione orario del 12 novembre autorizzata dal responsabile.''')
settings('statistiche', 'Filtri di analisi', '''stats.center|Centro statistiche|Seleziona un centro o tutti quelli autorizzati; il filtro persona richiede una sede singola.|Tutti i centri autorizzati.
stats.from|Dal mese|Inizio del periodo di confronto, incluso.|2026-01.
stats.to|Al mese|Fine inclusa del periodo; l’intervallo ammesso arriva a 24 mesi.|2026-12.
stats.role|Ruolo statistiche|Filtra per ruolo attuale dell’anagrafica.|Infermiere.
stats.person|Persona statistiche|Limita i risultati all’anagrafica del centro scelto.|Anna Esempio nel Centro A.''')
settings('esportazioni', 'Filtri Excel', '''export.kind|Prospetto Excel|Sceglie registro, totali, statistiche, fascicoli, onboarding o accordi; i permessi limitano le opzioni.|Onboarding e scadenze per l’inventario HR.
export.center|Centro esportazione|Sceglie il perimetro; il registro mensile richiede un solo centro.|Centro A per Presenze del singolo centro.
export.layer|Registro esportato|Per il registro mensile distingue Pianificato e Consuntivo.|Consuntivo per quanto svolto.
export.from|Dal mese esportazione|Primo mese o mese unico del registro; non si applica alla fotografia HR attuale.|2026-11.
export.to|Al mese esportazione|Ultimo mese dei prospetti di periodo, entro 24 mesi.|2026-12.''')
settings('carico', 'Conteggi aggregati', '''patient.day|Data conteggio|Data della rilevazione nel mese selezionato.|2026-11-12.
patient.slot|Fascia conteggio|Fascia cui si riferiscono pazienti e personale di confronto.|Mattina.
patient.ordinary|Pazienti ordinari|Numero intero non negativo, senza anagrafiche cliniche.|18.
patient.isolated|Pazienti in contumacia|Numero intero non negativo, pesato nel riferimento infermieristico.|2.''')


def build_catalog():
    extras = ROOT / 'docs/help_new_features.json'
    if extras.exists():
        payload = json.loads(extras.read_text())
        SETTINGS.extend(payload.get('settings', []))
        for key, changes in payload.get('topics', {}).items():
            current = next(t for t in TOPICS if t['id'] == key)
            current.update(changes)
    for source in sorted((ROOT / 'docs').glob('help_v011_*.json')):
        payload = json.loads(source.read_text())
        for item in payload.get('topics', []):
            if any(t['id'] == item['id'] for t in TOPICS):
                raise ValueError('Argomento duplicato: ' + item['id'])
            TOPICS.append(item)
        for key, changes in payload.get('topic_updates', {}).items():
            current = next(t for t in TOPICS if t['id'] == key)
            current.update(changes)
        for item in payload.get('settings', []):
            SETTINGS[:] = [x for x in SETTINGS if x['id'] != item['id']]
            SETTINGS.append(item)
    quality_file = ROOT / 'docs/help_quality.json'
    quality = json.loads(quality_file.read_text()) if quality_file.exists() else {}
    for key, changes in quality.get('topic_updates', {}).items():
        next(t for t in TOPICS if t['id'] == key).update(changes)
    for item in quality.get('settings', []):
        SETTINGS[:] = [x for x in SETTINGS if (x['topic'],x['id']) != (item['topic'],item['id'])]
        SETTINGS.append(item)
    for t in TOPICS:
        if (ROOT / 'assets/guide_screens' / (t['id']+'.webp')).exists():
            t['image']='/assets/guide_screens/'+t['id']+'.webp'
            t['image_caption']='Schermata di riferimento: '+t['title']
    result = {'version': quality.get('version','0.11'), 'language': 'it', 'topics': TOPICS, 'settings': SETTINGS, 'quickstarts': quality.get('quickstarts',[])}
    if (ROOT / 'assets/guida_illustrata.pdf').exists():
        result['manual_url']='/assets/guida_illustrata.pdf'
    return result


def write_text(catalog):
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "assets/guides").mkdir(exist_ok=True)
    (ROOT / 'docs/help_catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'assets/help_content.js').write_text('/* Generato da qa/generate_guides.py: contenuto locale, nessuna richiesta esterna. */\nwindow.NefroHelp = ' + json.dumps(catalog, ensure_ascii=False) + ';\n')
    lines = ['# NefroCenter '+catalog['version']+' — Guida d’uso illustrata', '',
             'Manuale operativo del portale centrale. Esempi e schermate usano dati dimostrativi. Le autorizzazioni sono sempre verificate dal servizio.', '',
             'Nel portale: **Guida** per la ricerca completa; **Aiuto pagina** per il tutorial contestuale. I video locali sono videoguide illustrate senza audio, con sottotitoli e trascrizione, non registrazioni di operazioni dal vivo.', '',
             '## Indice', '']
    if catalog.get('quickstarts'):
        lines += ['## Scegli un percorso', '']
        for route in catalog['quickstarts']:
            lines += ['### '+route['title']+' · '+route['role'], '', route['description'], '', ' → '.join('['+next(t['title'] for t in catalog['topics'] if t['id']==key)+'](#'+key+')' for key in route['topics']), '']
    for t in catalog['topics']:
        lines.append(f"- [{t['title']}](#{t['id']})")
    for t in catalog['topics']:
        lines += ['', f"<a id=\"{t['id']}\"></a>", f"## {t['title']}", '', f"**A chi serve:** {t['audience']}", '', t['goal'], '']
        if t.get('before'): lines += ['**Prima di iniziare:**', '']+['- '+v for v in t['before']]+['']
        if t.get('image'): lines += ['!['+t['title']+']('+t['image'].lstrip('/')+')', '', '*Schermata dimostrativa del portale.*', '']
        lines += [f'{i}. {s}' for i, s in enumerate(t['steps'], 1)]
        if t.get('example'): lines += ['', '**Esempio pratico:** '+t['example'], '']
        lines += ['', '**Risultato atteso:** ' + t['result'], '', '**Problemi frequenti:**', ''] + ['- ' + s for s in t['errors']]
        fields = [s for s in catalog['settings'] if s['topic'] == t['id']]
        if fields:
            lines += ['', '### Impostazioni e campi', '', '| Campo | Effetto | Esempio |', '|---|---|---|']
            for s in fields:
                lines.append('| ' + ' | '.join(s[k].replace('|', '\\|').replace('\n', '<br>') for k in ('label', 'effect', 'example')) + ' |')
        lines += ['', f"**Videoguida locale:** [video illustrato](assets/guides/{t['id']}.mp4) · [trascrizione](assets/guides/{t['id']}.txt)", '']
    (ROOT / 'GUIDE_UTENTE.md').write_text('\n'.join(lines))
    (ROOT / 'docs/GUIDE_UTENTE.md').write_text('# Guida d’uso\n\nIl manuale completo è [GUIDE_UTENTE.md](../GUIDE_UTENTE.md). Il catalogo verificabile è [help_catalog.json](help_catalog.json).\n')


if __name__ == '__main__':
    catalog=build_catalog()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--videos',action='store_true')
    parser.add_argument('--only-topic',action='append',choices=[t['id'] for t in TOPICS],
                        help='Rigenera solo questo video e conserva gli altri nel manifest; ripetibile')
    parser.add_argument('--screenshots',type=Path)
    args=parser.parse_args()
    if args.only_topic and not args.videos:
        parser.error('--only-topic richiede --videos')
    write_text(catalog)
    if args.videos:
        from render_guide_videos import build_videos as render_quality_videos
        render_quality_videos(catalog,args.screenshots,args.only_topic)
    print(f'{len(catalog["topics"])} tutorial e {len(catalog["settings"])} impostazioni documentati.',flush=True)
