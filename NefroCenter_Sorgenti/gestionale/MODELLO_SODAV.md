# Dal modello Sodav al registro web

Versione 0.6 · 15 ottobre 2026

Il registro riprende la struttura del file fornito: **una persona, tre righe mattina/pomeriggio/sera, giorni del mese in orizzontale e contatori a destra**. Le altre strutture possono attivare fasce e causali diverse. I calcoli economici sono separati dalla compilazione e hanno una chiave precisa: **persona + struttura + mese**.

## Cosa è stato letto

Fonte: `Presenze personale  Sodav Febbraio  2026 sodav.xlsm`.

SHA-256: `9cbf7e2a710d46831225d025cec190bb02b58e572eef76caddebf722a0c9a6ec`.

Sono stati analizzati i dati OOXML, le formule, i risultati già salvati nel file e le immagini del Vademecum. Il file originale non è stato modificato. **Excel e le macro VBA non sono stati eseguiti**: il confronto riguarda formule riconosciute e valori memorizzati, non un ricalcolo dell'intera cartella in Excel.

Il file contiene 17 anagrafiche riconosciute e 231 registrazioni: 194 turni di lavoro e 37 celle di assenza. Non contiene orari effettivi per questi turni. Il software importa le fasce e lascia gli orari vuoti; non presume che ogni turno equivalga a sei ore.

## Corrispondenza con il registro

| Nel file | Nel programma |
|---|---|
| `Da Compilare!C6`, `O6` | Struttura e mese |
| Colonne A/B e blocco di tre righe | Qualifica, persona, rapporto e fasce m/p/s |
| D:AH | Celle giornaliere; sono mostrati solo i giorni realmente esistenti nel mese |
| AI e contatore esterni | Turni lavorati e presenze fuori sede |
| AJ:AS e PL | Conteggi distinti per causale |
| AT | Conteggiabile economico secondo le causali selezionate nell'accordo; distinto dal numero dei soli turni lavorati |
| AV, AW, AY | Base dopo l'eventuale teorico, unità feriali e festive |
| AX, AZ, BA | Componenti economiche e risultato dell'accordo individuale |
| AU, note e importi manuali | Informazioni da verificare con l'amministrazione; nessuna conversione arbitraria in formula |

Nel registro, **Reg.** indica tutte le celle compilate. Non è chiamato AT perché AT cambia con l'accordo: alcune formule escludono RC, altre no. La scheda Accordi e calcoli mostra il conteggiabile effettivamente usato per la persona.

Giallo e verde, secondo il Vademecum, indicano lavoro in altra sede; il carattere rosso indica festivo riconosciuto. Nel programma diventano attributi espliciti, con testo accessibile oltre al colore. I colori ambigui sono segnalati per una verifica. Il responsabile deve specificare la sede esterna quando il colore non ne identifica il nome.

## Le differenze individuali trovate

Dieci blocchi nominativi hanno una combinazione di formule riconosciuta senza eseguire codice arbitrario:

| Regola nel file | Persone riconosciute |
|---|---:|
| Conteggiabile meno teorico, detrazione 100 | 7 |
| Conteggiabile meno teorico, senza detrazione | 1 |
| Tutto il conteggiabile, senza detrazione | 2 |
| Senza una formula economica riconosciuta completa | 7 |

Le tariffe presenti nelle dieci combinazioni sono 50 per l'unità feriale e 70 per la festiva. Sono informazioni del singolo modello, **non tariffe universali del gruppo**. I contatori dei festivi già riconosciuti non vengono automaticamente detratti: le formule BA riconosciute non li sottraggono. La relativa rettifica parte da zero e deve essere impostata esplicitamente se prevista dall'accordo.

Per ricostruire esattamente il conteggio di celle non vuote, le proposte riconosciute includono le causali non lavorate, con RC incluso o escluso secondo la specifica formula AT. Le nuove proposte generiche hanno invece una selezione visibile da verificare.

## Problemi del file che non vanno ereditati alla cieca

1. **Calendario:** X3 contiene 26 giorni. La formula usa un intervallo che prosegue oltre febbraio e un riferimento nel foglio nascosto con vecchie condizioni sui mesi. Per febbraio 2026, con settimana lunedì–sabato e senza festività aggiuntive pertinenti al mese, i giorni sono 24. L'elenco di festività del file contiene date del 2022 e 2023: non viene trasposto automaticamente al 2026.
2. **Riferimenti interrotti:** 21 formule contengono `#REF!`, nel foglio Per consulente. Questi risultati non vengono importati come output affidabili.
3. **ROL:** alcune formule contano E:AI, anziché l'intera griglia D:AH. Il programma conta tutte le celle di presenza del mese.
4. **Risultati negativi:** alcune formule producono valori negativi che il foglio Per consulente nasconde. Il programma li mantiene visibili e li segnala, senza azzerarli automaticamente.
5. **Collaboratori:** importi manuali, ritenute e contributi non costituiscono una regola uniforme ricostruibile. Non è stata introdotta una formula fiscale presunta e gli IBAN del foglio non vengono importati da questa procedura.

## Configurazione per persona, struttura e mese

In **Accordi e calcoli → Apri accordo** si possono impostare:

- Modello a turni, a ore o a quota fissa.
- Tutto il conteggiabile oppure differenza rispetto al teorico.
- Teorico dal calendario del centro oppure valore individuale del mese; ore giornaliere per il modello a ore.
- Tariffe feriali/festive, detrazione, integrazione fissa e rettifica positiva o negativa.
- Numero e rettifica unitaria dei festivi già riconosciuti, se applicabili.
- Causali non lavorate incluse e inclusione/esclusione delle presenze esterne.
- Conferma dell'accordo e motivazione della modifica.

Per il modello a ore si usano orari registrati e crediti minuti delle causali del periodo. In presenza di turni senza orari, l'importo a ore resta non calcolabile. Un periodo senza registrazioni non genera importi variabili; una quota fissa confermata può essere calcolata anche senza turni.

Ogni accordo è memorizzato nel periodo del centro, con versione, autore e data. Le modifiche alle tariffe generali non riscrivono gli accordi già salvati. Il mese successivo propone valori iniziali da confermare: **non è ancora presente un rinnovo automatico degli accordi né una decorrenza inframensile**. Se una persona lavora in due strutture, può avere due accordi distinti. Le anagrafiche restano associate ai centri; non è stato introdotto un sistema automatico di fusione dei dipendenti fra sedi.

Il compilatore non può leggere o modificare gli accordi tramite le API. Amministratore e responsabile autorizzato possono modificarli; il salvataggio richiede password e secondo fattore verificati negli ultimi cinque minuti, altrimenti viene richiesta una nuova conferma. Un mese chiuso blocca anche questi cambiamenti; ogni riapertura richiede una motivazione.

## Riscontro svolto

- Per tutti i **10 blocchi economici riconosciuti**, i conteggi AT e i risultati BA sono stati ricostruiti e confrontati con i valori salvati: **10/10 corrispondono**, usando per il confronto lo stesso teorico di 26 del file.
- Questo non conferma che 26 sia il teorico corretto: nel software il calendario effettivo restituisce 24 e il responsabile deve confermare il calendario o impostare un teorico individuale motivato.
- Tutti gli accordi importati restano **da confermare**, inclusi quelli riconosciuti. Le sette posizioni senza formule complete riconosciute richiedono una configurazione esplicita.
- Il pacchetto e l'anteprima non contengono anagrafiche reali, IBAN o copia del file originale. I casi di prova sono fittizi.

Questo è un modello gestionale delle presenze e degli accordi. Non è un motore paghe completo: elaborazioni fiscali, contributive o contrattuali non ricavabili dal file richiedono regole aggiuntive validate dai referenti.

## Come provarlo

Seguire `INSTALLAZIONE_WEB.md`. Dopo l'accesso con 2FA, l'amministratore apre **Centri → Importa modello Excel**, controlla l'anteprima e conferma. Quindi seleziona febbraio 2026, verifica Presenze e apre gli accordi individuali. L'importazione crea un centro dedicato e impedisce di importare due volte lo stesso file. Il calendario e gli accordi devono essere verificati prima di usare i risultati operativamente.
