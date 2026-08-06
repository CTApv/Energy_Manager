# Energy Manager

[![CI](https://github.com/CTApv/Energy_Manager/actions/workflows/ci.yml/badge.svg)](https://github.com/CTApv/Energy_Manager/actions/workflows/ci.yml)

Energy Manager è una piattaforma open source di monitoraggio energetico composta da un **Edge autonomo installato nel sito** e da una **Control Room opzionale** che concentra più Edge. È pensata per ecosistemi con fotovoltaico, accumulo, colonnine di ricarica, contatori, sensori meteo e utenze elettriche organizzate in una gerarchia monte/valle.

La release `0.9.1` aggiunge il **Digital Twin Lab** per pre-commissioning senza hardware: scenari energetici coerenti, simulazione multi-device, fault injection, stress test fino a 150 slave e checklist di qualificazione persistente. Conserva le fondamenta P0–P5 della linea 0.9.

## Maintainer e licenza

**Filippo Lolli** — sviluppatore e maintainer

[filippoctass@gmail.com](mailto:filippoctass@gmail.com)

Il progetto è distribuito con licenza [MIT](LICENSE). Crediti e attribuzioni sono in [CREDITS.md](CREDITS.md); la procedura di segnalazione vulnerabilità è in [SECURITY.md](SECURITY.md).

## Capacità principali

- dashboard dell'intero ecosistema e viste specialistiche per singolo dispositivo;
- albero energetico drag and drop con contatore a monte autorevole e somme a valle;
- pannello destro richiudibile con gerarchia, potenza, energia, stato e priorità;
- live data con gauge, indicatori e grafici adattati a multimetri, FV, storage, EV e meteo;
- storico, confronti omogenei, export CSV, KPI, budget e soglie con isteresi;
- fasce tariffarie con date di validità, orari, giorni, priorità, prelievo e immissione;
- baseline congelate, scostamento del periodo e metadati di normalizzazione;
- discovery Modbus guidata e provisioning distinto per TCP, RTU e RTU-over-TCP;
- catalogo driver read-only, ricorsivo e validato, con un file per modello o famiglia compatibile;
- ruoli applicati sia alla navigazione sia alle API;
- funzionamento Edge offline, outbox persistente e riallineamento alla riconnessione;
- Control Room multi-tenant per clienti, siti, flotta Edge, inventario e rollup;
- immagini Docker `linux/amd64` e `linux/arm64`.

## Architettura

```text
strumenti Modbus TCP / RTU
            |
            v
  +-----------------------+
  | Edge del sito         |
  | polling + SQLite      |
  | live/storico/allarmi  |
  | UI e commissioning    |
  +-----------+-----------+
              | HTTPS + bearer + HMAC
              | outbox, retry, idempotenza
              v
  +-----------------------+
  | Control Room          |
  | tenant / siti / Edge  |
  | portfolio + rollup    |
  | PostgreSQL            |
  +-----------------------+
```

L'Edge resta autorevole per acquisizione, configurazione strumenti e continuità locale. La Control Room è un concentratore e non è necessaria al funzionamento del sito. Le applicazioni condividono il pacchetto API ma il middleware espone solo le rotte ammesse dal relativo `EM_MODE`.

Approfondimenti: [architettura](docs/architecture.md) · [Control Room](docs/control-room.md) · [sicurezza](docs/security-architecture.md) · [ciclo di vita dati](docs/data-lifecycle.md).

## Avvio demo

Prerequisiti: Docker Engine o Docker Desktop con Compose.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

| Servizio | Indirizzo |
|---|---|
| Edge | http://localhost:3000 |
| OpenAPI Edge | http://localhost:8000/docs |
| Control Room | http://localhost:3001 |
| OpenAPI Control Room | http://localhost:8001/docs |
| Simulatore multimetro | `localhost:5020` · http://localhost:18090 |
| Simulatore inverter FV | `localhost:5021` · http://localhost:18091 |
| Simulatore accumulo | `localhost:5022` · http://localhost:18092 |
| Simulatore colonnina EV | `localhost:5023` · http://localhost:18093 |
| Simulatore meteo | `localhost:5024` · http://localhost:18094 |

Credenziali esclusivamente demo: `admin` / `EnergyDemo!2026`.

## Digital Twin Lab

Nel profilo demo, tecnici e amministratori trovano **Digital Twin Lab** nella navigazione Edge. Il laboratorio offre:

- sei scenari accelerabili, dalla villa solare al blackout controllato;
- un ecosistema coerente: `rete = consumi - fotovoltaico - accumulo`;
- 150 Unit ID del simulatore multimetro, con utenze 1–4 organizzabili monte/valle;
- fault controllati: offline, latenza, freeze, registri identici, NaN, reset contatori, perdita fase, squilibrio e picco;
- stress test a connessione condivisa o pool limitato, con successo, throughput e latenza p95;
- checklist e storico delle esecuzioni per rendere ripetibile il pre-commissioning.

Smoke test completo dopo l'avvio:

```powershell
.\scripts\digital-twin-smoke.ps1
```

Il laboratorio è disabilitato per default e viene rifiutato esplicitamente con `EM_ENVIRONMENT=production`. Dettagli e limiti: [Digital Twin Lab](docs/digital-twin-lab.md).

## Primo commissioning Edge

1. Aprire **Struttura impianto** e definire sito, dispositivi e gerarchia.
2. In **Comunicazioni** cercare gli endpoint Modbus o configurarli manualmente.
3. Per TCP diretto indicare l'IP sul dispositivo; per RTU e RTU-over-TCP condividere bus/gateway e assegnare Unit ID distinti.
4. Confermare modello, firmware, mappa registri, endianness, rapporti TA/TV e verso energia.
5. Associare il contatore generale e le utenze secondarie nell'albero.
6. Impostare allarmi, tariffe, baseline, potenza contrattuale e budget.
7. Verificare qualità dati, backup e checklist in **Verifica commissioning**.

La rimozione di un dispositivo richiede una conferma semplice e consente di mantenere lo storico scollegato dal live oppure cancellarlo. La procedura completa è in [docs/commissioning.md](docs/commissioning.md).

## Installazione Edge cliente

Il profilo cliente non avvia simulatori o Control Room, non inserisce demo e richiede segreti univoci.

```powershell
.\scripts\new-customer-env.ps1 -Hostname energy-manager.cliente.local
New-Item -ItemType Directory -Force data | Out-Null
docker compose -f docker-compose.edge.yml up -d --build
```

Lo script genera anche un `EM_EDGE_ID` UUID persistente. Non riutilizzarlo tra siti e non rigenerarlo durante un aggiornamento.

## Installazione Control Room

Generare un `.env` protetto e avviare:

```powershell
.\scripts\new-control-room-env.ps1 -Hostname control.energy.example
docker compose -f docker-compose.control-room.yml up -d --build
```

Creare cliente, sito ed Edge dalla Control Room. Il token di enrollment è mostrato una sola volta. In produzione ogni Edge deve usare credenziali proprie; il token globale resta soltanto una compatibilità di bootstrap della release corrente.

## Modbus e catalogo

I dati vengono tradotti in chiavi semantiche, per esempio `electrical.active_power.total` ed `electrical.energy.import_total`. In questo modo dispositivi di marche diverse hanno la stessa esperienza in dashboard, mentre produttore e modello restano visibili.

Driver inclusi:

- Siemens SENTRON PAC2200, PAC3200 e PAC3220;
- Schneider Electric Acti9 iEM3000;
- Huawei SUN2000/SUN5000 LB0 con LUNA2000;
- ABB Terra AC;
- template di laboratorio per multimetro, FV, storage, EV e meteo.

I file sono in `packages/modbus-catalog/profiles/drivers/`; il contratto è in [profile.schema.json](packages/modbus-catalog/schema/profile.schema.json). Ogni profilo dichiara il livello reale di evidenza: non verificato, simulato, revisionato da manuale, testato su hardware o validato sul campo. Le mappe simulate non sostituiscono la verifica sul manuale esatto del produttore. Dettagli: [driver](docs/device-drivers.md) e [discovery](docs/modbus-discovery.md).

## Sincronizzazione e dati

Il contratto Edge → Control Room `1.0` contiene batch deterministici, eventi con ID stabile, inventario e salute Edge. Il corpo canonico è firmato HMAC-SHA256 e autenticato con bearer token; Control Room deduplica batch ed eventi prima di salvare campioni e rollup al minuto.

Retention predefinita:

- campioni Edge: 730 giorni;
- outbox già consegnata: 30 giorni;
- raw Control Room: 30 giorni;
- rollup Control Room: 3650 giorni.

Le finestre sono configurabili. I backup hanno una policy separata: vedere [docs/data-lifecycle.md](docs/data-lifecycle.md).

## Ruoli

| Ruolo | Ambito tipico |
|---|---|
| Visualizzatore | dashboard, live, storico, KPI e allarmi in consultazione |
| Operatore | consultazione operativa e gestione degli eventi consentiti |
| Amministratore cliente | preferenze, utenti, conformità, tariffe e baseline |
| Tecnico | impianto, comunicazioni, driver, diagnostica e commissioning |
| Amministratore piattaforma | governance completa e portfolio Control Room |

Le pagine non consentite non vengono renderizzate nel menu; l'API verifica nuovamente il ruolo.

## Sicurezza e limiti

Sono presenti Argon2, JWT, RBAC, audit, CORS ristretto, CSP, HTTPS, HMAC, idempotenza, segreti obbligatori in produzione, profili Modbus read-only e audit dipendenze in CI.

La release è pronta per commissioning applicativo, non certifica automaticamente un impianto o un'organizzazione. Restano fuori dal perimetro attivo: MFA/SSO, vault centralizzato, SBOM firmata, OTA firmato, provider Tailscale reale, notifiche multicanale e protocolli non Modbus. La sezione Transizione 4.0/5.0 raccoglie evidenze e readiness, ma non sostituisce perizie, verifiche fiscali o certificazioni.

## Sviluppo e test

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".\apps\api[test]"
.\.venv\Scripts\python -m pytest -q apps\api\tests

Set-Location apps\web
npm ci
npm run build
```

Stack: Python 3.13, FastAPI, SQLAlchemy 2, Alembic, React 18, TypeScript, Vite, SQLite Edge e PostgreSQL 17 Control Room.

## Repository

```text
apps/api/                 API, polling, report, sync e migrazioni
apps/web/                 interfacce Edge e Control Room
packages/modbus-catalog/  driver, template e schema
simulators/               slave Modbus TCP di laboratorio
infrastructure/           reverse proxy e runtime
scripts/                  provisioning e operazioni
docs/                     architettura e procedure
.github/                  CI, aggiornamenti e template PR
```

Prima di una consegna cliente eseguire sempre test con gli strumenti reali, Site Acceptance Test, backup/restore e revisione dei rischi di rete OT.
