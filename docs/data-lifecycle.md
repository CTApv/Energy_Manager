# Ciclo di vita dei dati

| Livello | Origine | Conservazione predefinita | Scopo |
|---|---|---:|---|
| campione Edge | polling locale | 730 giorni | diagnosi e report di sito |
| outbox consegnata | Edge | 30 giorni | audit della sincronizzazione |
| campione raw Control Room | ingest firmato | 30 giorni | dettaglio e troubleshooting |
| rollup 1 minuto | ingest Control Room | 3650 giorni | portfolio e trend lunghi |
| marker idempotenza | ingest | come raw Control Room | prevenzione duplicati |

Le finestre sono configurabili con `EM_TELEMETRY_RETENTION_DAYS`, `EM_SENT_OUTBOX_RETENTION_DAYS`, `EM_CONTROL_RAW_RETENTION_DAYS` ed `EM_ROLLUP_RETENTION_DAYS`. La manutenzione elimina a lotti i record scaduti. I backup non sono automaticamente soggetti alla stessa retention: la loro policy va definita nel registro dei trattamenti e nelle procedure del cliente.

La cancellazione di un dispositivo può mantenere lo storico scollegato dalla vista live oppure cancellarlo definitivamente. La scelta deve essere coerente con obblighi contrattuali, fiscali e privacy applicabili.
