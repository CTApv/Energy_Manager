# Architettura MVP

Energy Manager è un monorepo indipendente. Lo stesso package Python viene eseguito con `EM_MODE=edge` oppure `EM_MODE=control-room`; le istanze usano database, processi e responsabilità differenti.

```text
Dispositivi Modbus TCP/RTU
          │ read-only
          ▼
 Simulatore ──► Edge API ──► SQLite + cache live/outbox
                    │                 │
                    │ API             │ batch HTTPS, retry/backoff
                    ▼                 ▼
                 Edge Web       Control Room API ──► PostgreSQL
                                      │
                                      ├── Control Room Web
                                      └── TailscaleProvider (fake/API boundary)
```

## Confini

- Il polling vive solo sull'Edge. La Control Room non apre connessioni Modbus.
- Catalogo (`DeviceProfile`) e installazione (`Device`) sono separati.
- L'albero di comunicazione deriva da `Connection`/`Device`; l'albero energetico usa `AssetNode`/`MeasurementBinding`.
- Ogni campione conserva UTC di campionamento e ricezione, qualità, errore e origine.
- L'outbox è persistente. Un batch ha UUID e la Control Room memorizza `IngestedBatch` per accettare retry idempotenti.
- `TailscaleProvider` separa modalità fake e integrazione reale. `NetworkAgent` usa argomenti separati, `shell=False` e dry-run.
- I contratti HTTP sono consultabili nelle OpenAPI locali `/docs` e `/openapi.json`.

## Sicurezza

Password e token Edge sono hashati con Argon2; le sessioni usano JWT firmati e scadenza. RBAC protegge le mutazioni, le viste flotta applicano il tenant dell'utente, i webhook sono verificati con HMAC e gli endpoint sensibili hanno rate limiting in memoria. CORS è ristretto tramite variabile d'ambiente.

