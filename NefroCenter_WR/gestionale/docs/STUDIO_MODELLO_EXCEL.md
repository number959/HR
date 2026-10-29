# Il modello Excel mensile delle presenze: come funziona e come il portale lo sostituisce

Studio del file «Presenze Personale <Struttura> <Mese> <Anno> – consulenti.xlsm» (modello Sodav/NefroCenter), eseguito sul file reale di un mese del 2026. Qui non compaiono nomi, importi individuali o coordinate bancarie: solo la struttura del file e il suo funzionamento. Obiettivo: **il portale fa tutto quello che fa il file**, così le strutture non compilano più l'Excel e l'ufficio del personale non lo rielabora.

## 1. Che cos'è il file

Una cartella di lavoro Excel con macro (`.xlsm`), una per struttura e per mese. La compila la struttura (presenze giorno per giorno), la completa l'ufficio del personale (importi), e da essa si ricavano due «uscite»: il foglio per il **consulente paghe** (cedolini dei dipendenti) e il prospetto dei **collaboratori** a prestazione (compensi da pagare con fattura o tramite associazione).

| Foglio | Visibile | Ruolo |
|---|---|---|
| **Vademecum** | sì | guida alla compilazione (immagini con 10 regole) |
| **Da Compilare** | sì, protetto | il registro vero e proprio: griglia, contatori, spazio ufficio del personale, indicatori, pazienti, note, festività |
| **Foglio1** | nascosto | costanti per le macro (colori di riferimento, codici m/p/s, giorni del mese) |
| **Collaboratori** | sì | compensi dei collaboratori a prestazione, con IBAN |
| **Per consulente** | nascosto | copia del registro con gli importi, destinata al consulente paghe (riempita da un pulsante) |

Nel file studiato: 19 persone riconoscibili, 417 registrazioni nel mese, 31 giorni di pazienti per fascia, 9 righe nel prospetto collaboratori, 16 formule con riferimenti interrotti (`#REF!`), tutte le formule delle macro in errore (`#NAME?`) perché il file era stato salvato da un programma senza macro.

## 2. Il Vademecum (regole per chi compila)

1. Sbloccare il file al primo uso (proprietà → annulla blocco).
2. Disattivare il completamento automatico di Excel, altrimenti «m» diventa «ma» e i conteggi si falsano.
3. I turni svolti **in un'altra sede** vanno colorati con sfondo **giallo** (o verde come seconda scelta): contano come turni della persona ma non come presenza nella struttura.
4. Il mese si cambia con un doppio clic sulla cella del mese: il calendario si aggiorna da solo.
5. A inizio mese ricolorare la griglia con carattere nero, per togliere i festivi del mese precedente.
6. Il file **non segnala i festivi**: chi compila deve mettere in **rosso** il carattere dei turni svolti in giorno festivo.
7. Usare solo i codici della legenda in alto.
8. Turni in **minuscolo** (m, p, s), assenze in **MAIUSCOLO**.
9. Per aggiungere una persona copiare un blocco di tre righe e incollarlo sopra il nominativo, altrimenti le formule si rompono.
10. Per le prestazioni indicare mansione e tipo di rapporto (libero professionista, volontario, associazione…).

Nel portale queste regole spariscono o diventano automatiche: i codici si scelgono da un elenco, la sede esterna è un campo, il festivo è un segno, il calendario è calcolato, le persone si aggiungono dal fascicolo, il tipo di rapporto è un campo del fascicolo.

## 3. Il foglio «Da Compilare»

### Intestazione

- Legenda delle assenze: FE ferie, PS permessi, ROL, RC recupero turno, MA malattia, MT maternità, PH legge 104, IN infortunio, AL allattamento, AG assenza giustificata, PL permesso lutto, AS aspettativa non retribuita (più FG, presente nei contatori ma non in legenda).
- `X3` **Giorni lavorativi** = `NETWORKDAYS.INTL(primo del mese, primo + giorni del mese, 11, elenco festività)`: giorni da lunedì a sabato meno le festività dell'elenco in fondo al foglio (righe 181–195). Nel file l'elenco era fermo al **2023**: per il mese del 2026 nessuna festività veniva tolta.
- Parametri: posti dialisi accreditati (10), posti letto, posti contumaciali (1), pazienti di riferimento per infermiere (5) e per medico (20).
- `C6` struttura, `O6` mese (data), `AB6` anno; `BD9` ultimo giorno del mese; riga 7 numeri dei giorni, riga 8 giorno della settimana.

### Griglia

Ogni persona occupa **tre righe** (m = mattina, p = pomeriggio, s = sera): colonna A qualifica (INF, MED, DS, AMM, AUT, AUS; «CS» sulla seconda riga segnala la caposala), colonna B nome e, sotto, tipo di contratto o chi fattura (per i collaboratori: «FATTURA», nome dell'associazione…), colonne D–AH i 31 giorni. Nella cella: il codice del turno (minuscolo) o dell'assenza (maiuscolo); sfondo giallo = fuori sede; carattere rosso = festivo.

### Contatori per persona (colonne AI–AT)

| Colonna | Formula | Significato |
|---|---|---|
| AI (prima riga) | `COUNTIF(m) + COUNTIF(p) + COUNTIF(s)` | turni di lavoro |
| AI (seconda riga) | `ContaCellePerColore(griglia, giallo)` (macro) | turni fuori sede |
| AJ…AS | `COUNTIF(griglia, "FE")`, …, `"PH"` | assenze per causale (FE, PS, ROL, FG, RC, MA, MT, AL, IN, PH); `PL` sulla seconda riga |
| AT | `93 − COUNTBLANK(griglia) − RC` | registrazioni totali (93 = 31 giorni × 3 fasce), senza i recuperi turno |

### Spazio riservato all'ufficio del personale (colonne AU–BC)

| Colonna | Formula | Significato |
|---|---|---|
| AU | testo | note «Accordi»: incentivi, importi netti pattuiti, «Applico −2» / «Non applico −2» (franchigia di 2 turni sui turni oltre il teorico) |
| AV Giorni extra | `AT − X3` (dipendenti) oppure `AT` (collaboratori: tutti i turni) | turni oltre i giorni lavorativi |
| AW Feriali | `AV − AY` | extra feriali |
| AX Netto | `AW × 50` | importo feriale (tariffa 50 €) |
| AY Festivi | `ContaCellePerColoreCarattere(griglia, rosso)` (macro) | turni in rosso |
| AZ Netto | `AY × 70` | importo festivo (tariffa 70 €) |
| BA Totale | `AX + AZ − 100 − 70 × BB` (dipendenti) oppure `AX + AZ` (collaboratori) | totale da comunicare al consulente: detrazione fissa 100 € e festivi già riconosciuti dal CCNL (70 € ciascuno) |
| BB:BC Festivi da CCNL | `COUNTA` delle celle compilate dall'ufficio | festivi già pagati dal contratto |

### Sezioni e totali

«Personale dipendente» (infermieri), «Infermieri a prestazione / Volontari / Dipendenti altri centri», riga «Totali turni infermieri» (somma dei contatori per causale; i turni di lavoro = totale − assenze), personale amministrativo, note; poi un secondo blocco con la stessa intestazione per «Medici dipendenti» e «Medici consulenti», con «Totali medici», «Totali infermieri» e «Totali personale».

### Indicatori per fascia (righe 76–90 per gli infermieri, 153–167 per i medici)

Per ogni giorno:

- **Infermieri in turno** per fascia = `TrovaTurni(codice, colore di riferimento «nessuno», colonna del giorno)`: conta solo le celle con quel codice **senza sfondo colorato**, cioè i turni svolti nella struttura (i gialli, fuori sede, sono esclusi).
- **Pazienti** per fascia e **Pazienti in contumacia** per fascia: inseriti a mano.
- **Rapporto pazienti / infermiere** = `(pazienti + contumacia × 5) / infermieri in turno` (il paziente in isolamento pesa come 5); per i medici `(pazienti + contumacia) / medici` (senza peso).
- **Efficienza** = rapporto / pazienti di riferimento (5 per infermiere, 20 per medico). Formattazione condizionale: ≥ 0,92 un colore, sotto un altro.
- Totali del mese: **Totale turni da lavorare** (somma dei turni in sede), **Totale dialisi da effettuare** (somma dei pazienti), **Media parametro** (media dei rapporti mensili delle tre fasce), **Efficienza media**.

### Altro

Protezione del foglio con password (celle di formula bloccate), stampa orizzontale ridotta al 36 %, pulsante «Crea Elaborazione per Consulente», elenco festività in fondo (B181–B195), collegamenti a query esterne non usati.

## 4. Il foglio nascosto «Foglio1»

Costanti per le macro: la cella «senza colore» di riferimento (A2), i codici m/p/s (C2, E2, G2), il giallo di riferimento (I2), il rosso di riferimento per il carattere (M2), un rosso di sfondo (K2, «COLORE3», non usato dalle formule) e `C3` = giorni del mese meno uno, scritto come catena di `IF` su date fisse del 2022–2023 (`"29"`, `"27"`, `"30"`): **fragile**, perché per i mesi non previsti vale sempre 30.

## 5. Le macro VBA

| Macro | Cosa fa |
|---|---|
| `TrovaTurni(codice, cellaColore, intervallo)` | conta le celle uguali al codice e con lo stesso colore di sfondo della cella di riferimento (= nessun colore): turni svolti nella struttura |
| `ContaCellePerColore(intervallo, cellaColore)` | conta le celle con lo sfondo del riferimento (giallo): turni fuori sede |
| `ContaCellePerColoreCarattere(intervallo, cellaColore)` | conta le celle non vuote con il carattere del riferimento (rosso): turni festivi |
| `SommaCellePerColore`, `SommaCellePerColoreCarattere`, `TrovaColoreCella`, `TrovaColoreCarattere`, `TrovaFestivi` | funzioni di servizio (una contiene un errore: assegna il risultato alla funzione sbagliata) |
| `CopiaSheet`, `CopiaEuro`, `Copiacedisannuovo`, `CopiaFormatoValore` | copiano intervalli della griglia (valori e colori) nel foglio «Per consulente»: versioni diverse con intervalli fissi, da adattare a mano quando cambiano le righe |
| `AggInf` | duplica un blocco di tre righe per aggiungere una persona |

Tutte le macro sono «volatili»: senza Excel con macro abilitate il file mostra `#NAME?` ovunque, e il consulente riceve un file da ricalcolare.

## 6. Il foglio «Collaboratori»

Un prospetto dei compensi per chi non è dipendente: qualifica, collaboratore, turni feriali e festivi, **importo lordo**, **ritenuta d'acconto**, **contributo ENPAPI 4 %**, **importo netto**, note, **IBAN**. Due gruppi: «prestazioni con fattura» (liberi professionisti) e «assistenza socio sanitaria» (tramite associazione), più una riga di «altre competenze» e il totale complessivo. Gli importi sono **scritti a mano**: dai dati si ricavano tariffe per turno diverse per persona e qualifica (per esempio feriale/festivo distinte per infermieri, medici e ausiliari), la ritenuta al 20 % per i professionisti e il netto = lordo − ritenuta. Il foglio non ha formule tranne i totali.

## 7. Il foglio «Per consulente»

Copia del registro (griglia, contatori, spazio ufficio del personale, festivi CCNL) riferita al foglio principale con formule, più i valori copiati dalle macro. In testa la nota al consulente: l'importo della colonna **Totale** è quello da considerare per i cedolini e lo schema dei **Festivi da CCNL** indica i festivi da retribuire. È il documento che l'ufficio del personale manda ogni mese al consulente paghe.

## 8. Fragilità del file (perché conviene sostituirlo)

- Festivi e sede esterna dipendono da **colori messi a mano**; un colore sbagliato cambia gli importi.
- Le macro non funzionano fuori da Excel desktop con macro abilitate (il file studiato le aveva tutte in errore).
- L'elenco delle festività era vecchio di tre anni; `C3` ha date fisse; i giorni lavorativi possono risultare sbagliati di uno (nel mese studiato: 26 invece di 25 per una festività caduta di sabato).
- La stessa persona può comparire due volte con qualifiche diverse; le celle possono contenere valori fuori legenda (un «1» al posto di un codice); i blocchi copiati male spostano le formule (`#REF!`).
- Le tariffe dei collaboratori e le ritenute sono a mano, senza storico né controllo.
- Nessun controllo di sovrapposizioni, riposo minimo, mesi chiusi, chi ha modificato cosa.

## 9. Corrispondenza con il portale

| Nel file | Nel portale |
|---|---|
| Griglia persone × giorni × fasce, codici | **Registro presenze** (vista mese e giorno), causali dai parametri della struttura |
| Sfondo giallo = fuori sede | campo **sede** della registrazione (le sedi esterne sono nei parametri) |
| Carattere rosso = festivo | segno **festivo** della registrazione; le festività del calendario sono calcolate |
| Giorni lavorativi X3 | **giorni lavorativi del calendario** della struttura (giorni della settimana e festività nei parametri, nazionali precalcolate) |
| Contatori per causale, totali per gruppo | **Conteggi del mese** in «Controlli e chiusura» (per persona e per gruppo infermieri/medici/altri) |
| Giorni extra, feriali, festivi, tariffe 50/70, detrazione 100, festivi CCNL, «−2» | **Accordi e calcoli**: modello a turni, base «oltre il teorico» o «tutti i turni», tariffe, detrazione fissa, festivi CCNL, correzione del teorico (franchigia), quota fissa e conguaglio per incentivi e importi pattuiti |
| Infermieri/medici in turno, pazienti, rapporto, efficienza, medie | **Pazienti e carico per fascia** in «Controlli e chiusura»: stessi calcoli (peso dell'isolamento solo per gli infermieri, riferimenti 5 e 20, soglia 0,92), sintesi del mese |
| Posti dialisi, posti contumaciali, pazienti di riferimento | **Parametri della struttura** (carico per fascia) |
| Sezioni dipendenti / collaboratori, «FATTURA», associazione | **tipo di rapporto** e **chi fattura** nel fascicolo (schede Contratto e Amministrazione) |
| Foglio «Collaboratori» | pagina **Collaboratori e compensi**: lordo dall'accordo, ritenuta e cassa con le percentuali del fascicolo, netto, IBAN, totali, Excel |
| Foglio «Per consulente» | **Foglio mensile come il modello Excel** (Esportazioni): registro, per consulente, collaboratori, generato dai dati senza formule né macro; in più **Paghe** per il tracciato del consulente |
| Note «Accordi» | note dell'accordo e del fascicolo |
| Pulsante «Crea elaborazione» e macro | scaricamento del foglio mensile |
| Vademecum | guida in linea, manuale e videoguide |
| Protezione del foglio | ruoli e permessi, mese chiuso, approvazione mensile, storico delle modifiche |

## 10. Il mese senza Excel

1. La struttura registra ogni giorno turni e assenze nel registro (dal PC o dal telefono), indicando la sede quando il turno è fuori e il segno festivo quando serve; registra i pazienti per fascia (ordinari e in isolamento).
2. Il responsabile controlla «Controlli e chiusura»: conteggi, pazienti e carico, avvisi; conferma calendario e parametri.
3. L'ufficio del personale conferma gli accordi del mese («Accordi e calcoli»): tariffe, franchigia, festivi CCNL, incentivi; vede gli importi.
4. Il mese viene chiuso (o approvato, se la struttura usa l'approvazione).
5. Dalle Esportazioni si scarica il **foglio mensile** per il consulente paghe e il prospetto dei **collaboratori** per i pagamenti; da Paghe l'eventuale tracciato.

## 11. Da decidere con l'azienda

- Le **tariffe reali** di ciascun collaboratore (il file ne usa di diverse per persona) e le percentuali di ritenuta e cassa: vanno inserite nei fascicoli e negli accordi; il portale non le inventa.
- Il significato esatto di «Applico −2» (nel portale: correzione del teorico di +2 giorni, cioè i primi due turni oltre non si pagano) e delle note «2 D», «3D» del foglio Collaboratori.
- Le qualifiche «AUT», «AUS», «CS» (caposala): nel portale sono ruoli o qualifiche del fascicolo, da definire nei parametri.
- Se il consulente paghe accetta il nuovo foglio mensile così com'è o vuole un tracciato (pagina Paghe).
- Il peso dell'isolamento per i medici (nel file non pesa) e la soglia di efficienza 0,92: il portale li tiene come parametri modificabili.

L'**importazione** del vecchio file resta disponibile solo per caricare i mesi passati o per la transizione: non è il modo di lavorare del portale.
