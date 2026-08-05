# Energy Manager

Energy Manager è una piattaforma open source per la gestione di ecosistemi energetici evoluti, composta da un **Edge autonomo installato sul posto** e da una **Control Room opzionale** che concentra più Edge senza sostituirne le funzioni locali.

[![CI](https://github.com/CTApv/Energy_Manager/actions/workflows/ci.yml/badge.svg)](https://github.com/CTApv/Energy_Manager/actions/workflows/ci.yml)

La release `0.8.0` aggiunge un contesto energetico live sempre disponibile, separa correttamente TCP diretto, RTU seriale e RTU-over-TCP e rende il commissioning coerente con la topologia fisica dell’impianto.

## Sviluppo e manutenzione

**Filippo Lolli** — sviluppatore e maintainer del progetto.

Contatto: [filippoctass@gmail.com](mailto:filippoctass@gmail.com)

I riferimenti completi e l'ambito dei crediti sono riportati in [CREDITS.md](CREDITS.md). La presenza dei crediti non definisce da sola i termini di licenza o di utilizzo del software.

## Cosa offre

- dashboard live dell’intero impianto o del singolo dispositivo;
- pannello destro richiudibile con albero live, totali energetici, stato e priorità operative in ogni vista Edge;
- albero energetico modificabile con drag and drop e principio “contatore a monte autorevole”;
- catalogo Siemens PAC2200/PAC3200/PAC3220, Schneider Acti9 iEM3000, Huawei SUN2000/SUN5000 LB0 con LUNA2000 e ABB Terra AC, con protocolli e varianti dichiarati dal costruttore;
- discovery guidata della rete Modbus con scelta esplicita tra dispositivo TCP diretto e gateway RTU-over-TCP;
- profili estendibili per multimetri, inverter fotovoltaici, accumuli, colonnine e dispositivi di altri produttori;
- monitoraggio per giorno, settimana, mese e anno con confronto omogeneo col periodo precedente;
- costi di prelievo, ricavi da immissione, costo netto, emissioni e proiezioni di budget;
- produzione FV, energia autoconsumata, autoconsumo e autosufficienza;
- ripartizione dei consumi per utenza, quota non attribuita e consumi fuori orario;
- storico interrogabile, grafici per grandezza ed export CSV compatibile con Excel;
- soglie con isteresi, severità, presa visione, chiusura e audit;
- interfaccia e azioni adattate al ruolo, backup verificabili, retention e checklist di commissioning;
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
| Simulatore multimetro | `localhost:5020` · controllo http://localhost:18090 |
| Simulatore inverter FV | `localhost:5021` · controllo http://localhost:18091 |
| Simulatore accumulo | `localhost:5022` · controllo http://localhost:18092 |
| Simulatore colonnina EV | `localhost:5023` · controllo http://localhost:18093 |
| Simulatore stazione meteo | `localhost:5024` · controllo http://localhost:18094 |

Credenziali esclusivamente demo:

```text
utente: admin
password: EnergyDemo!2026
```

Al primo accesso:

1. aprire **Configura impianto** e definire sito, connessione, dispositivi e gerarchia;
2. usare **Trova dispositivi** per cercare automaticamente gli endpoint Modbus oppure configurarli manualmente, indicando se sono dispositivi TCP diretti o slave dietro un gateway RTU-over-TCP;
3. associare `electrical.energy.import_total` al contatore generale e alle utenze secondarie;
4. aprire **Consumi e costi → Parametri** e impostare tariffa, fattore CO₂, potenza e budget;
5. verificare dati e qualità nei **Dispositivi live**;
6. completare **Messa in servizio** prima della consegna.

## Monitoraggio energetico

Il motore usa chiavi normalizzate, non indirizzi Modbus o nomi proprietari. Per questo un Siemens PAC e uno strumento competitor vengono presentati nello stesso modo; cambiano solo produttore e modello.

I profili di laboratorio completi espongono 57 misure per il multimetro trifase, 30 per l’inverter FV, 28 per l’accumulo, 25 per la colonnina e 22 per la stazione meteo. Includono tensioni e correnti di fase, cosφ, potenze ed energie, armoniche, stringhe FV, celle e limiti BMS, sessione EV e variabili atmosferiche. Sono mappe simulate e non sostituiscono i driver verificati dei produttori.

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

Il polling è read-only e tratta i trasporti secondo la topologia reale: ogni dispositivo Modbus TCP diretto possiede il proprio IP e la propria sessione; RTU seriale e RTU-over-TCP condividono invece un bus/gateway, serializzano le richieste e identificano i dispositivi tramite Unit ID. Timeout e retry restano controllati.

Il pulsante **Comunicazioni → Ricerca Modbus** apre un browser di rete simile ai commissioning tool industriali: scansiona una rete privata fino a `/24`, cerca le porte configurate, interroga fino a 32 Unit ID e usa la funzione Modbus Device Identification quando disponibile. Il modello suggerito deve sempre essere confermato dalla targhetta. La discovery non scrive registri e non installa nulla senza conferma. Dettagli e limiti di sicurezza sono in [docs/modbus-discovery.md](docs/modbus-discovery.md).

## Provisioning dell'impianto Edge

La configurazione è separata in percorsi coerenti con il lavoro del tecnico e dell'Energy Manager:

- **Struttura impianto**: identità del sito, dispositivi installati e albero energetico monte/valle;
- **Comunicazioni**: canali Modbus TCP, bus Modbus RTU/RS485, rilevamento porte COM e ricerca automatica;
- **Preferenze**: lingua, aggiornamento UI, calendario energetico, tariffe, potenza contrattuale e budget;
- **Stato sistema**: release, host, database, storage e capacità locale;
- **Verifica commissioning**: controllo conclusivo prima della consegna.

La rimozione mostra prima l'impatto e richiede una sola conferma. Le associazioni nell'albero vengono scollegate automaticamente; l'utente sceglie chiaramente se conservare lo storico per analisi e confronti futuri (opzione consigliata) oppure cancellare definitivamente tutti i campioni.

## Ruoli ed esperienza adattiva

La sicurezza non si limita a disabilitare i pulsanti: ogni sessione vede solo le sezioni utili al proprio incarico e le API applicano nuovamente l'autorizzazione sul server.

| Ruolo | Esperienza principale |
|---|---|
| Visualizzatore | Dashboard, live, storico, KPI e allarmi in sola consultazione |
| Operatore | Consultazione operativa e presa in carico degli eventi consentiti |
| Amministratore cliente | Monitoraggio, preferenze, stato Edge, conformità e gestione utenti |
| Tecnico | Provisioning, comunicazioni, catalogo, regole, diagnostica e commissioning |
| Amministratore piattaforma | Accesso completo, inclusa governance e gestione remota |

Le voci non autorizzate non vengono inserite nel menu. Se un ruolo cambia durante una nuova sessione, la navigazione viene ricostruita e un'eventuale pagina non più consentita viene sostituita dalla dashboard.

I profili IPv4 delle schede rilevate possono essere preparati da **Comunicazioni → Rete Edge**. Il profilo viene conservato e marcato come in attesa di applicazione: l'applicazione sul sistema operativo richiede il servizio host Edge e resta disabilitata nei normali container (`EM_NETWORK_MANAGEMENT_ENABLED=false`) per evitare modifiche accidentali all'interfaccia dalla quale è aperta la sessione.

I profili supportano boolean/bit field, interi 16/32/64 bit, float 32/64, ASCII, byte/word order, scala, offset, enum e misure derivate. La validazione blocca funzioni di scrittura, sovrapposizioni e definizioni incoerenti.

- driver Siemens SENTRON PAC: `packages/modbus-catalog/profiles/drivers/multimeters/siemens-sentron-pac.yaml`;
- driver Schneider Acti9: `packages/modbus-catalog/profiles/drivers/multimeters/schneider-acti9-iem3000.yaml`;
- driver Huawei ibrido: `packages/modbus-catalog/profiles/drivers/hybrid/huawei-sun2000-lb0-luna.yaml`;
- driver ABB Terra AC: `packages/modbus-catalog/profiles/drivers/ev-chargers/abb-terra-ac.yaml`;
- profili generici non destinati al commissioning: `packages/modbus-catalog/profiles/templates/`;
- schema: `packages/modbus-catalog/schema/profile.schema.json`.

Il catalogo segue il principio **un file per driver o famiglia realmente compatibile**. Più modelli possono convivere nello stesso file soltanto quando condividono implementazione e blocchi di registri; `compatibility_group` e `register_map` rendono esplicito il confine. Il caricatore esplora ricorsivamente il catalogo, registra il file sorgente nel profilo e blocca gli ID duplicati all'avvio. La convenzione completa è descritta in [docs/device-drivers.md](docs/device-drivers.md).

Ogni profilo reale include URL del manuale, data di verifica, firmware/modelli compatibili e avvertenze. La mappa registri deve comunque essere confrontata con targhetta, manuale esatto, firmware e variante di comunicazione installata. Fronius e SolarEdge vengono riconosciuti come famiglie SunSpec, ma non sono associati a indirizzi fissi finché il runtime non avrà discovery del modello e scale factor dinamici: usare registri “probabili” sarebbe pericoloso in commissioning.

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
