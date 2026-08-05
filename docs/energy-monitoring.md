# Motore di monitoraggio energetico

Questo documento descrive le regole applicate dalla release 0.3.0. Serve a rendere verificabili i numeri mostrati in dashboard e a evitare interpretazioni diverse durante il commissioning.

## Sorgente autorevole

Il contatore generale è il primo dispositivo attivo associato con ruolo `primary` alla misura `electrical.energy.import_total`; viene preferito un binding su un nodo di categoria `meter`. La sua energia è il totale autorevole dell’impianto. I sotto-contatori spiegano la ripartizione, non vengono sommati al generale.

```text
energia non attribuita = energia generale − somma energie sotto-contatori
```

Un valore negativo segnala normalmente doppio conteggio, gerarchia errata, basi temporali non allineate o rapporti TA/TV incoerenti e richiede verifica.

## Delta dei contatori

Per ogni periodo viene letta anche l’ultima misura valida precedente all’inizio, necessaria come baseline. Sono usati solo campioni con qualità `good` e valore numerico.

- incremento normale: `lettura corrente − lettura precedente`;
- reset rilevato: viene usata la lettura corrente come incremento e la qualità diventa `estimated`;
- dati insufficienti: valore assente con qualità `missing`.

Giorno e settimana seguono il calendario nel fuso configurato. Mese e anno iniziano rispettivamente il primo giorno del mese e il primo gennaio. Il periodo precedente è calendarizzato e limitato allo stesso tempo trascorso del periodo corrente.

## Indicatori economici e ambientali

```text
costo prelievo = energia importata × tariffa media di prelievo
ricavo immissione = energia esportata × valorizzazione media
costo netto = costo prelievo − ricavo immissione
emissioni = energia importata × fattore kgCO₂e/kWh
```

Tariffe e fattore emissivo sono dati configurabili del cliente, non valori normativi incorporati nel software. Devono riportare fonte, periodo di validità e approvazione nel verbale di impianto.

## Fotovoltaico

La produzione è la somma dei contatori `pv.energy.total` dei dispositivi attivi classificati `pv_inverter`.

```text
autoconsumo energetico = max(0, produzione FV − energia esportata)
consumo totale = energia importata + autoconsumo energetico
indice di autoconsumo = autoconsumo energetico / produzione FV
indice di autosufficienza = autoconsumo energetico / consumo totale
```

Le formule presuppongono contatori import/export e produzione riferiti allo stesso confine, periodo e fuso orario.

## Potenza e qualità

Media, minimo e picco usano i campioni validi di `electrical.active_power.total`. La copertura stima il tempo osservato limitando ogni intervallo fra due campioni a 30 secondi: buchi più lunghi non vengono considerati coperti. Il superamento contrattuale confronta il picco misurato con la potenza configurata; non sostituisce la logica tariffaria del distributore.

## Fuori orario e budget

Ogni incremento di energia viene attribuito all’istante della lettura finale. È fuori orario se cade in un giorno non lavorativo o al di fuori dell’intervallo configurato. La proiezione mensile estrapola il consumo maturato sui giorni del mese e ha valore indicativo, soprattutto nei primi giorni o con carichi stagionali.

## Export

L’endpoint `/api/energy/report.csv` produce CSV UTF-8 con BOM e separatore `;`, includendo KPI, ripartizione e serie temporale. L’export usa gli stessi calcoli della dashboard e richiede autenticazione.
