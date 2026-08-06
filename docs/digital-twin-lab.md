# Digital Twin Lab e pre-commissioning

Il Digital Twin Lab serve a verificare configurazione, acquisizione, qualità dati, gerarchia, storico e comportamento sotto carico quando l'hardware reale non è disponibile. È un banco software ripetibile, non sostituisce FAT, SAT o confronto con il display dello strumento.

## Ecosistema virtuale

I cinque simulatori — multimetro, inverter FV, accumulo, colonnina EV e meteo — leggono lo stesso orologio virtuale e lo stesso stato d'impianto. Ad ogni istante vale:

```text
potenza rete = consumi del sito - produzione FV - potenza accumulo
```

La potenza accumulo è positiva in scarica e negativa in carica. Nel blackout controllato il PCS virtuale segue il carico residuo e la rete resta a zero. Sul multimetro, l'Unit ID 1 rappresenta il generale; gli ID 2, 3 e 4 rappresentano pompa di calore, elettrodomestici e servizi/EV, la cui somma coincide con il generale. Gli ID 5–150 espongono carichi distinti per lo stress test.

## Scenari

| Scenario | Scopo |
|---|---|
| Villa solare | Produzione diurna, autoconsumo e carica accumulo |
| Nuvolosità variabile | Transitori FV e cicli batteria |
| Inverno efficiente | Pompa di calore, poco sole, picchi mattina/sera |
| Picco serale | EV e carichi domestici contemporanei |
| Turno produttivo | Profilo industriale diurno |
| Blackout controllato | Funzionamento virtuale in isola |

Il tempo può essere accelerato da `0,1x` a `86400x` e riposizionato su una data/ora deterministica.

## Fault injection

Sono disponibili disconnessione per Unit ID, latenza, freeze dei registri, valori tutti uguali, NaN, reset del contatore, perdita fase, squilibrio di tensione e picco di potenza. L'anomalia dei registri tutti uguali è riconosciuta dal polling anche quando i singoli valori ricadono casualmente in intervalli plausibili: il dispositivo passa a `degraded` con motivo `implausible_identical_registers`.

I fault possono essere rimossi senza ricreare container o dispositivi. Ogni azione effettuata dalla UI produce audit e una run persistente.

## Stress e qualificazione

Lo stress test supporta da 1 a 150 slave e due modalità:

- `shared_gateway`: una sola sessione TCP serializza gli Unit ID, equivalente a RTU-over-TCP;
- `bounded_pool`: distribuisce il carico su un massimo di 32 connessioni, evitando connection storm.

Il risultato comprende richieste attese/riuscite, throughput, latenza minima/media/p95/massima, valori distinti ed errori. La qualificazione controlla raggiungibilità dei simulatori, bilancio energetico, dispositivi acquisiti, storico e pressione dell'outbox.

## Uso

Avvio completo:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
.\scripts\digital-twin-smoke.ps1
```

Lo smoke test verifica sempre API, scenario, fault injection e 100 slave; riporta inoltre la checklist del database corrente. Per trasformare anche quest'ultima in un gate bloccante usare `-RequireQualification`. Un ambiente di sviluppo già utilizzato può fallire il gate, per esempio per un outbox storico accumulato, senza invalidare il banco Modbus.

L'abilitazione è governata da `EM_DIGITAL_TWIN_ENABLED`. Il compose demo la imposta a `true`; il valore predefinito, il compose cliente e l'ambiente production la mantengono disabilitata.

## Gate prima del sito cliente

Una run software superata dimostra che il percorso applicativo è coerente nelle condizioni simulate. Prima della consegna restano obbligatori almeno: modello e firmware reali, cablaggio e terminazioni, parametri TCP/seriali, rapporti TA/TV, segno delle energie, confronto con riferimento, prova perdita comunicazione, backup/restore e verbale SAT.
