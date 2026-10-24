# Verifica di Persone e Presenze Web 0.7

Consegna del 17 ottobre 2026. Versione candidata alla revisione, collaudata localmente su Linux. L’app non è stata pubblicata su un server aziendale o su Internet. Le prove applicative usano dati inventati; il modello Excel fornito è stato letto separatamente e importato solo in un database temporaneo, poi eliminato.

## Risultati

**77 test automatici superati**, oltre al percorso end-to-end nel browser con un servizio Waitress reale. La suite verifica logica, permessi, autenticazione, importazione, calcoli, concorrenza e ripristino. Il risultato non costituisce una certificazione di sicurezza o una garanzia di assenza di difetti.

| Area | Test | Esito |
|---|---:|---|
| Presenze, parametri, importazione e autorizzazioni | 25 | Superati |
| Fascicolo HR, onboarding, allegati e concorrenza | 13 | Superati |
| Servizio web, 2FA, sessioni, ruoli e ripristino | 25 | Superati |
| Accordi individuali e riconoscimento delle formule | 12 | Superati |
| Migrazione e annullamento atomico | 2 | Superati |

I test comprendono: accesso negato prima del secondo fattore, TOTP con vettori RFC 6238, scadenza e anti-riutilizzo, recuperi monouso anche concorrenti, limitazione persistente dei tentativi, segreti cifrati, chiave errata, cookie/CSRF/origine, conferma recente delle operazioni sensibili, revoca delle sessioni, isolamento fra centri e divieto di accesso HR per compilatore e lettore.

La nuova prova di ripristino copia il backup in una directory pulita, verifica integrità e riferimenti del database, rilegge fascicolo e allegato e controlla l’accesso 2FA con la chiave corretta. La chiave errata viene rifiutata. `after-restore` e l’invalidazione dei codici preesistenti sono coperti da test dedicati.

## Difetti riprodotti e corretti

| Difetto | Correzione e prova |
|---|---|
| Una risposta lenta poteva riaprire il dipendente selezionato in precedenza | Controllo della richiesta corrente; prova con due risposte deliberatamente fuori ordine |
| Cambi rapidi di centro o mese potevano mostrare una risposta precedente | Controllo della richiesta di stato corrente; prova con due centri e risposta ritardata |
| Un valore non valido in una sezione HR nascosta bloccava il salvataggio senza mostrare il campo | Apertura della sezione interessata e validazione visibile; prova con email aziendale non valida |
| Navigazione e doppi comandi durante il salvataggio potevano interferire con la scheda | Blocco temporaneo dei comandi, contesto della scrittura fissato e ripristino dei controlli al termine |
| Caricamento allegati sensibile a cambi di selezione durante la lettura del file | Acquisizione preventiva di centro, persona, categoria e scadenza; navigazione protetta durante la scrittura |
| Il selettore dello stile si comprimeva troppo su mobile | Riga e larghezza minima dedicate; verifica a 390 e 320 pixel |
| I vecchi fascicoli non contenevano i nuovi campi | Completamento dei campi mancanti alla lettura conservando dati e checklist; test di compatibilità |

È stato inoltre aggiunto un test di salvataggi HR concorrenti: una sola versione viene accettata e il secondo aggiornamento obsoleto è respinto, mantenendo coerente lo storico.

## Dati dipendenti

Il fascicolo dispone di **53 campi standard**, di cui 17 aggiunti, oltre ai campi personalizzati del centro. Le otto sezioni sono Anagrafica, Recapiti, Contratto, Amministrazione, Qualifiche, Onboarding, Documenti e Scadenze. Sono presenti documento di identità, dati contrattuali, IBAN e intestatario, contatti, qualifiche, checklist, allegati e collegamenti alle presenze e all’accordo mensile.

Verificati salvataggio e rilettura, propagazione del contratto al registro, email e date del documento, scadenze, checklist e allegato PDF dimostrativo. La validazione IBAN controlla formato e checksum; non verifica l’intestazione del conto. La checklist organizza le verifiche e non invia comunicazioni amministrative né produce firme digitali. Gli accordi non sostituiscono un software paghe.

## Browser e interfacce

Percorso reale con Chromium e Waitress: attivazione riservata, password personale, TOTP, dieci recuperi, nuovo dipendente, modifica del fascicolo, onboarding, allegato, presenza, riepilogo in dashboard e accordo individuale. Verificati anche nuovo compilatore, attivazione del suo 2FA, rifiuto delle API HR e rientro dell’amministratore con un recupero.

Tutte le otto sezioni HR sono state percorse nei quattro stili a **1400, 1024, 390 e 320 pixel**. Verificati persistenza dello stile, ritorno ad Attuale, assenza di overflow orizzontale esterno, registro mensile, accordi e sicurezza su mobile. Le tabelle larghe possono scorrere nel proprio contenitore. Controllati ordine da tastiera nel login, errori JavaScript e violazioni CSP nel percorso provato. Le schermate principali sono state ispezionate visivamente.

L’anteprima in conversazione è separata dal servizio: dati fittizi, stato locale e 2FA simulata esplicita. Le quattro varianti sono state provate a 1024/390/320 pixel in chiaro e scuro, con modifica dati, nuovo dipendente, centri, profili, presenze, accordi e onboarding. Il movimento ridotto è rispettato. L’app installabile offre quattro composizioni chiare: l’adattamento chiaro/scuro dell’anteprima non implica un tema scuro implementato nel servizio.

## Riscontro sul modello Excel

La prova della 0.7 sul modello Sodav di febbraio 2026 ha importato **17 persone e 231 registrazioni**, di cui 194 lavorative e 37 di assenza, nelle fasce m/p/s. Restano 17 accordi da confermare e nessun importo automaticamente approvato. Le 194 registrazioni lavorative senza orari rimangono segnalate; non sono state convertite arbitrariamente in giornate da sei ore.

Per le 10 combinazioni di formule riconosciute, AT e BA corrispondono ai valori salvati nel file: **10 confronti su 10**, usando il teorico manuale di 26 del modello. Il calendario di febbraio 2026 restituisce invece 24 giornate secondo i giorni lavorativi configurati. Il confronto non approva il calendario né le condizioni economiche individuali. Le altre sette posizioni richiedono definizione dell’accordo. Le anomalie della fonte sono descritte in `MODELLO_SODAV.md`.

Excel e VBA non sono stati eseguiti: il confronto usa formule riconosciute e valori memorizzati. Il file originale è rimasto invariato. Il pacchetto non contiene il foglio originale né dati del personale importato. `qa/source-check.json` riporta solo esiti aggregati e impronta della fonte.

## Grafica, risorse e gratuità

Spazio di lavoro, Essenziale ed Editoriale sono implementati con CSS e JavaScript nativi. Attuale conserva l’aspetto precedente. Nessuna nuova libreria di produzione è stata aggiunta. Le transizioni sono leggere e rispettano il movimento ridotto.

| Risorsa usata | Contributo | Licenza conservata |
|---|---|---|
| Roboto | Tipografia | OFL-1.1 |
| Lucide Static 0.468.0 | Icone | ISC; attribuzione Feather MIT |
| Waitress 3.0.2 | Servizio HTTP applicativo | ZPL-2.1 |
| PyOTP 2.9.0 | Secondo fattore TOTP | MIT |
| Segno 1.6.6 | Generazione locale del QR | BSD-3-Clause |
| cryptography 50.0.2 | Cifratura dei segreti TOTP | Apache-2.0 oppure BSD-3-Clause |

Editoriale usa anche Georgia, font di sistema di cui non vengono distribuiti i file. Il logo NefroCenter resta una risorsa del gruppo, non un asset open source. Provenienza e attribuzioni sono in `assets/resources.json`, `dependencies.json`, `assets/` e `licenses/`.

L’app non richiede abbonamenti software. Deve comunque essere ospitata e gestita su un computer/server raggiungibile dalle sedi. Nessun servizio a pagamento è stato attivato.

## Pacchetto e rollback

Controllati sintassi Python e JavaScript, integrità ZIP e impronte SHA-256 dei file. Il pacchetto contiene codice, dipendenze incluse, licenze, istruzioni e test. Sono esclusi database, chiavi, cache, ambienti virtuali e dati personali reali. `qa/README.md` descrive come ripetere i test; la cartella `qa/` conserva gli esiti. Chromium e Playwright servono solo al collaudo e non sono distribuiti nell’app.

`Presenze_Web_v0.6_Rollback.zip` è identico all’originale. **Stile → Attuale** ripristina immediatamente l’aspetto. Il rollback completo richiede codice, database e chiave corrispondenti al momento precedente all’aggiornamento; seguire `ROLLBACK.md` per conservare anche le modifiche successive. Non è stato effettuato un rollback su un server dell’organizzazione.

## Limiti del collaudo

Restano da provare HTTPS con certificato reale, collegamenti dalle sedi, server Windows, scansione del QR con telefono fisico, carico simultaneo atteso, alta disponibilità e altri browser. Le intestazioni HTTPS e i cookie Secure sono coperti dai test WSGI; il percorso nel browser usa HTTP sul solo loopback. Non è stato svolto un audit indipendente di sicurezza o accessibilità.

Prima dell’uso operativo occorrono collaudo del server e della rete, verifica dei parametri individuali, prova di riavvio e ripristino nell’ambiente destinato all’uso e confronto con gli archivi delle sedi. Il numero massimo di centri/utenti non è stato dimensionato. SQLite è locale al server e il portale usa un unico processo applicativo. Database HR e allegati non sono cifrati integralmente dall’app: la cifratura applicativa riguarda i segreti 2FA.
