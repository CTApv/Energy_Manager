# Energy Manager — Edge + Control Room MVP

MVP funzionante per acquisizione Modbus industriale, storico locale, KPI energetici e sincronizzazione opzionale verso una Control Room. Il progetto non contiene né dipende da codice PV Guardian.

## Gestione dell'impianto sull'Edge

L'impianto si configura dall'interfaccia Edge, voce **Impianto** nel menu laterale. La pagina raccoglie in un percorso unico:

1. identità del sito;
2. connessioni Modbus TCP o RTU;
3. dispositivi installati e relativo profilo di catalogo;
4. albero energetico;
5. associazione delle misure normalizzate ai nodi.

Per installare uno strumento si usa il percorso **Impianto → Dispositivi**: categoria, produttore, connessione/protocollo e infine modello. La connessione scelta filtra i soli modelli compatibili e indica se l'interfaccia è integrata, una variante del prodotto o richiede un modulo opzionale.

La Control Room non è il luogo in cui configurare l'impianto locale: resta separata e verrà evoluta come concentratore e supervisore degli Edge.

## Console operativa Edge

La Dashboard Edge è una console live con aggiornamento automatico ogni 5 secondi. Permette di selezionare lo strumento, visualizzare KPI e andamento della potenza, controllare qualità e tempi di acquisizione, consultare tutte le misure normalizzate e gestire gli allarmi. Le pagine **Dati live** e **Allarmi** riutilizzano la stessa esperienza specializzata.

Le soglie supportano condizioni sopra/sotto limite, priorità, isteresi anti-chattering, attivazione/disattivazione, notifica nel centro Edge, presa visione dell'operatore, rientro automatico e audit delle modifiche. Le regole lavorano sulle chiavi normalizzate e restano quindi indipendenti dal produttore del multimetro. Canali esterni come SMTP, SMS o webhook non vengono presentati come attivi finché non sono configurati con credenziali reali.

La vista live segue l'albero energetico configurato in **Impianto → Albero e misure**. Si può selezionare l'intero impianto oppure ogni singolo multimetro. La politica di calcolo è `upstream_meter_authoritative_else_sum_children`: se un nodo dispone di un generale a monte, la sua misura è il totale autorevole e i sotto-contatori ne rappresentano la ripartizione; se manca il misuratore del nodo, il valore viene ricostruito sommando i figli. Sono mostrati potenza/energia attribuite, residuo non monitorato e copertura di misura. Il bilancio energetico usa delta omogenei sulle ultime 24 ore, evitando di sommare letture assolute con basi temporali diverse.

La sezione **Governance → Conformità 4.0 / 5.0** esegue un readiness assessment esplicito, non una certificazione. La matrice copre Transizione 4.0/5.0, ISO 50001/50006, metrologia MID, IEC 62443/NIS2, Cyber Resilience Act, EU Data Act, continuità e ISA-18.2. Ogni controllo mostra evidenza disponibile e prossima azione; l'export produce un fascicolo JSON con impronta SHA-256. Il contenuto va riesaminato alla data dell'investimento con professionisti abilitati e fonti MIMIT/GSE vigenti.

## Avvio rapido

Prerequisito: Docker con Compose.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Aprire:

- Edge: http://localhost:3000
- Control Room: http://localhost:3001
- OpenAPI Edge: http://localhost:8000/docs
- OpenAPI Control Room: http://localhost:8001/docs
- controlli simulatore: `GET/POST http://localhost:18090`

Credenziali demo per entrambe le interfacce:

```text
utente: admin
password: EnergyDemo!2026
```

Cambiare password, `EM_SECRET_KEY`, `EM_EDGE_TOKEN`, `EM_WEBHOOK_SECRET` e password PostgreSQL prima di qualunque deployment non locale. Nessun segreto reale è incluso.

## Verifica del flusso verticale

Il seed crea `CTA Demo`, `Stabilimento Demo`, `EM-DEMO-001`, quattro dispositivi e due alberi distinti. Il polling parte automaticamente ogni 5 secondi:

```text
Simulatore Modbus TCP → Edge → profilo catalogo → polling
→ misure normalizzate → SQLite/storico → KPI monte/valle
→ SyncOutbox → Control Room/PostgreSQL
```

La Control Room può essere fermata senza interrompere l'Edge:

```powershell
docker compose stop control-room-api control-db
# attendere: l'Edge continua e SyncOutbox cresce
docker compose start control-db control-room-api
# il retry con backoff recupera i batch mancanti
```

Controllare gli scenari del simulatore:

```powershell
Invoke-RestMethod http://localhost:18090
Invoke-RestMethod -Method Post -ContentType application/json `
  -Body '{"anomaly":true,"unattributed_percent":25}' `
  http://localhost:18090
Invoke-RestMethod -Method Post -ContentType application/json `
  -Body '{"anomaly":false,"unattributed_percent":18,"reset_unit":1}' `
  http://localhost:18090
```

Il profilo demo è in `packages/modbus-catalog/profiles/generic-meter-v1.yaml`. Il catalogo Siemens PAC2200/PAC3200/PAC3220 è in `packages/modbus-catalog/profiles/siemens-pac-family.yaml`: contiene registri di misura, qualità, stato, domanda ed energia supportati dal polling read-only FC03/FC04. La validazione rifiuta funzioni di scrittura, sovrapposizioni, tipi/dimensioni incoerenti e profili invalidi prima dell'attivazione.

I registri dei produttori vengono convertiti in chiavi e unità comuni, per esempio `electrical.active_power.total` in kW ed `electrical.energy.import_total` in kWh. Dashboard, KPI, allarmi e binding consumano queste chiavi: aggiungere un competitor cambia produttore/modello mostrato, non la struttura della dashboard.

## Sviluppo locale e test

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".\apps\api[test]"
.\.venv\Scripts\python -m pytest -q apps\api\tests

Set-Location apps\web
npm install
npm run build
```

Le immagini usano Python 3.13, Node 22 in build e componenti runtime multi-arch disponibili per AMD64/ARM64. SQLite è usato sull'Edge e PostgreSQL 17 nella Control Room. Alembic applica la baseline `0001_initial` a ogni avvio.

## Funzioni implementate

- modelli dati Edge e Control Room con UUID e UTC;
- autenticazione Argon2/JWT, ruoli, audit, CORS ristretto, rate limit e firma HMAC webhook;
- catalogo JSON/YAML con schema, versioni, duplicazione, export e preview decoder;
- decoder boolean/bit field, interi 16/32/64, float 32/64, ASCII, byte/word order, scala, offset ed enum;
- connessioni TCP/RTU configurabili; polling MVP reale TCP read-only, blocchi contigui, timeout, stato/errori e pausa dispositivo;
- storico con qualità/provenienza e cache live interrogabile;
- albero energetico separato, binding multipli, spostamento via API ed eliminazione protetta;
- delta contatori con reset/overflow, disponibilità comunicazione e KPI energia non attribuita;
- regole/eventi allarme e chiusura dall'API;
- outbox persistente, batch, retry/backoff e idempotenza Control Room;
- attivazione monouso a scadenza e Tailscale fake, diagnostica dry-run e webhook;
- UI responsive Edge e Control Room con tutte le sezioni MVP;
- simulatore Modbus TCP per generale, Linea 1, Linea 2 e macchina industriale.

## Limiti noti dell'MVP

Il polling implementa Modbus TCP e Modbus RTU; TCP è verificato con il simulatore, mentre RTU richiede ancora collaudo su adattatore RS485/hardware reale e un lock condiviso per porta prima dell'uso industriale. Il catalogo resta intenzionalmente read-only: configurazione, scrittura e reset dei registri del multimetro non sono abilitati. Il simulatore espone controlli per anomalia, reset e quota non attribuita; la disconnessione selettiva del singolo slave e il timeout artificiale sono predisposti nello stato ma non alterano ancora il server. Le pagine amministrative meno centrali usano viste tabellari API; l'editor visuale avanzato e il drag-and-drop sono post-MVP. Il provider Tailscale reale è un confine sicuro intenzionalmente non attivato senza credenziali/autorizzazione.

Per dettagli: [architettura](docs/architecture.md) e [backlog](docs/backlog.md).
