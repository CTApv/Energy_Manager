# Architettura della piattaforma

Energy Manager è un monorepo con due prodotti runtime. Lo stesso package Python viene avviato con `EM_MODE=edge` o `EM_MODE=control-room`; database, processi, rotte e autorità rimangono distinti.

## Edge

L'Edge è installato nel sito e funziona senza Internet. Gestisce connessioni Modbus, driver, polling, normalizzazione, albero energetico, live, storico, report, KPI, allarmi, backup e commissioning. SQLite mantiene configurazione e telemetria; l'outbox registra gli eventi da inviare.

Per TCP diretto ogni dispositivo possiede endpoint IP/porta. RTU seriale e RTU-over-TCP condividono invece il bus o gateway e usano Unit ID distinti. Il polling è serializzato per canale e limitato a funzioni read-only.

## Contratto di sincronizzazione

Il batch `schema_version: 1.0` contiene:

- `batch_id` deterministico e `edge_id` UUID stabile;
- campioni con `event_id`, `sample_id`, timestamp, qualità e origine;
- versione applicativa, versione configurazione, backlog e disco libero;
- inventario normalizzato dei dispositivi.

Il corpo JSON canonico è firmato HMAC-SHA256 e trasmesso via HTTPS con il token individuale dell'Edge. La Control Room verifica l'identità prima di elaborare il corpo e applica deduplica sia al batch sia ai singoli eventi.

## Control Room

La Control Room gestisce tenant, siti, enrollment Edge, salute flotta, inventario remoto, campioni raw e rollup. PostgreSQL è il database previsto. Non apre connessioni Modbus e non sostituisce i processi dell'Edge.

Le query portfolio ricavano il perimetro dagli Edge consentiti all'utente. L'interfaccia permette di creare clienti, siti ed Edge, generare credenziali monouso, navigare la gerarchia e ispezionare dispositivi replicati.

## Componenti condivisi

- `DeviceProfile` descrive un driver; `Device` descrive un'installazione.
- `Connection` descrive un canale; l'endpoint TCP diretto resta sul dispositivo.
- `AssetNode` e `MeasurementBinding` definiscono l'albero energetico indipendentemente dalla rete.
- ogni campione conserva tempo di misura/ricezione, qualità, errore e origine;
- i contratti HTTP sono pubblicati nelle OpenAPI locali.

## Scelte ancora evolutive

La separazione è oggi applicativa e di deployment, non ancora in pacchetti sorgente indipendenti. Per una Control Room ad alta scala saranno necessari coda ingest, replica, osservabilità distribuita e aggregazioni multilivello. Vedere [backlog.md](backlog.md).
