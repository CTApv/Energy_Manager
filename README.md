# Energy Manager

Energy Manager è una piattaforma open source per il monitoraggio energetico industriale, composta da un **Edge autonomo installato in impianto** e da una **Control Room opzionale** che concentra più Edge senza sostituirne le funzioni locali.

[![CI](https://github.com/CTApv/Energy_Manager/actions/workflows/ci.yml/badge.svg)](https://github.com/CTApv/Energy_Manager/actions/workflows/ci.yml)

La release `0.3.0` acquisisce misure Modbus, le normalizza indipendentemente dal costruttore, conserva lo storico locale e trasforma i contatori in informazioni operative: consumi, potenza, costi, CO₂, budget, confronto temporale, bilancio fotovoltaico e ripartizione per utenza.

## Cosa offre

- dashboard live dell’intero impianto o del singolo dispositivo;
- albero energetico modificabile con drag and drop e principio “contatore a monte autorevole”;
- catalogo Siemens PAC2200, PAC3200 e PAC3220, con varianti Modbus TCP/RTU compatibili;
- profili estendibili per multimetri, inverter fotovoltaici, accumuli, colonnine e dispositivi di altri produttori;
- monitoraggio per giorno, settimana, mese e anno con confronto omogeneo col periodo precedente;
- costi di prelievo, ricavi da immissione, costo netto, emissioni e proiezioni di budget;
- produzione FV, energia autoconsumata, autoconsumo e autosufficienza;
- ripartizione dei consumi per utenza, quota non attribuita e consumi fuori orario;
- storico interrogabile, grafici per grandezza ed export CSV compatibile con Excel;
- soglie con isteresi, severità, presa visione, chiusura e audit;
- utenti e ruoli, backup verificabili, retention e checklist di commissioning;
- funzionamento Edge anche senza Internet, con outbox e sincronizzazione successiva;
- immagini Docker multi-arch `linux/amd64` e `linux/arm64`.

## Architettura

```text
Strumenti Modbus TCP/RTU
          │
          ▼
┌──────────────────────────────────────────┐
│ Edge cliente                             │
│ polling → normalizzazione → SQLite       │
│ live → storico → report → allarmi        │
│ UI locale + backup + commissioning       │
└───────────────────┬──────────────────────┘
                    │ outbox firmata, retry/idempotenza
                    ▼
┌──────────────────────────────────────────┐
│ Control Room opzionale                   │
│ concentratore Edge e supervisione flotta │
│ PostgreSQL                               │
└──────────────────────────────────────────┘
```

La configurazione fisica e logica dell’impianto si esegue sempre sull’Edge. La Control Room riceve gli eventi degli Edge e offre una vista aggregata multi-cliente/multi-sito.

## Avvio demo in 3 minuti

Prerequisiti: Docker Engine o Docker Desktop con Compose.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Servizi disponibili:

| Servizio | Indirizzo |
|---|---|
| Edge | http://localhost:3000 |
| API Edge / OpenAPI | http://localhost:8000/docs |
| Control Room | http://localhost:3001 |
| API Control Room / OpenAPI | http://localhost:8001/docs |
| Simulatore Modbus | `192.168.2.108:5020` dall’impianto o `localhost:5020` dall’host |
| Controllo simulatore | http://localhost:18090 |

Credenziali esclusivamente demo:

```text
utente: admin
password: EnergyDemo!2026
```

Al primo accesso:

1. aprire **Configura impianto** e definire sito, connessione, dispositivi e gerarchia;
2. associare `electrical.energy.import_total` al contatore generale e alle utenze secondarie;
3. aprire **Consumi e report → Parametri** e impostare tariffa, fattore CO₂, potenza e budget;
4. verificare dati e qualità nella **Console dispositivi**;
5. completare **Commissioning** prima della consegna.

## Monitoraggio energetico

Il motore usa chiavi normalizzate, non indirizzi Modbus o nomi proprietari. Per questo un Siemens PAC e uno strumento competitor vengono presentati nello stesso modo; cambiano solo produttore e modello.

| Informazione | Chiave normalizzata principale |
|---|---|
| Potenza attiva totale | `electrical.active_power.total` |
| Energia importata | `electrical.energy.import_total` |
| Energia esportata | `electrical.energy.export_total` |
| Produzione fotovoltaica | `pv.energy.total` |

I consumi derivano dalla differenza tra letture cumulative. Un reset del contatore non genera un valore negativo: l’incremento successivo viene conservato e marcato `estimated`. I campioni invalidi non contribuiscono al report. Il confronto usa lo stesso tempo trascorso nel periodo precedente, evitando di confrontare metà mese con un mese completo.

Per dettagli su formule, segni e assunzioni: [docs/energy-monitoring.md](docs/energy-monitoring.md).

## Installazione Edge presso un cliente

Il profilo cliente non avvia simulatori o Control Room, non inserisce dispositivi demo, richiede segreti non predefiniti e pubblica soltanto il gateway HTTPS.

```powershell
.\scripts\new-customer-env.ps1 -Hostname energy-manager.cliente.local
New-Item -ItemType Directory -Force data | Out-Null
docker compose -f docker-compose.edge.yml up -d --build
```

Prima dell’avviamento definitivo:

- usare account nominativi e cambiare ogni credenziale iniziale;
- verificare rapporto TA/TV, verso energia, unità, endianness e revisione firmware;
- evitare polling paralleli sullo stesso slave o gateway;
- sincronizzare l’orologio Edge tramite NTP;
- provare ogni soglia con il referente di impianto;
- creare un backup e verificarne l’integrità;
- esportare e firmare il verbale di Site Acceptance Test.

La procedura completa è in [docs/commissioning.md](docs/commissioning.md). La sezione **Conformità 4.0 / 5.0** è un readiness assessment con evidenze esportabili, non una certificazione fiscale, metrologica o normativa.

## Modbus e catalogo dispositivi

Il polling è read-only e supporta Modbus TCP e RTU con sessione condivisa per connessione, serializzazione delle richieste, timeout e retry controllati. In questo modo decine di dispositivi sullo stesso gateway non aprono una connessione TCP indipendente ciascuno.

I profili supportano boolean/bit field, interi 16/32/64 bit, float 32/64, ASCII, byte/word order, scala, offset, enum e misure derivate. La validazione blocca funzioni di scrittura, sovrapposizioni e definizioni incoerenti.

- catalogo PAC: `packages/modbus-catalog/profiles/siemens-pac-family.yaml`;
- profilo demo: `packages/modbus-catalog/profiles/generic-meter-v1.yaml`;
- schema: `packages/modbus-catalog/schema/profile.schema.json`.

La mappa registri deve sempre essere confrontata con il manuale esatto del modello, versione firmware e variante di comunicazione installata.

## Sicurezza e continuità

- password Argon2 e token JWT con ruoli;
- audit delle operazioni sensibili;
- CORS ristretto, security header e rate limit sugli endpoint sensibili;
- firma HMAC e idempotenza dei batch Edge → Control Room;
- segreti obbligatori in produzione e verifica anti-placeholder all’avvio;
- HTTPS nel deployment cliente;
- database locale, retention configurabile e backup SQLite consistente con SHA-256;
- readiness e health check distinti.

Non inserire segreti reali nel repository. Generare `.env.customer` con lo script fornito e conservarlo con permessi limitati.

## Sviluppo e test

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".\apps\api[test]"
.\.venv\Scripts\python -m pytest -q apps\api\tests
```

Frontend:

```powershell
Set-Location apps\web
npm ci
npm run build
```

Stack principale: Python 3.13, FastAPI, SQLAlchemy 2, Alembic, React 18, TypeScript, Vite, SQLite sull’Edge e PostgreSQL 17 nella Control Room.

## Struttura del repository

```text
apps/api/                 API, polling, report, persistenza e migrazioni
apps/web/                 interfacce Edge e Control Room
packages/modbus-catalog/  profili e schema dispositivi
simulators/               slave Modbus TCP di laboratorio
infrastructure/           reverse proxy e configurazione runtime
scripts/                  provisioning e verifiche operative
docs/                     architettura, commissioning e backlog
.github/workflows/        CI e build multi-arch
```

## Stato e limiti dichiarati

La piattaforma è pronta per il commissioning applicativo, ma ogni installazione richiede qualifica sul campo. Modbus RTU deve essere provato con l’adattatore RS485 e lo strumento reali. Tariffe multi-fascia, notifiche esterne, OTA firmato, SSO e provider Tailscale reale restano evoluzioni pianificate e non vengono presentate come attive.

Documenti utili: [architettura](docs/architecture.md) · [monitoraggio energetico](docs/energy-monitoring.md) · [commissioning](docs/commissioning.md) · [backlog](docs/backlog.md).
