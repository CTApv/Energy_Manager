# Control Room

La Control Room concentra una flotta di Edge senza assumere il controllo del polling locale. Gestisce tenant, siti, identità Edge, salute della flotta, inventario remoto e serie aggregate.

## Autorità

- L'Edge è autorevole per dispositivi, gerarchia, connessioni e campioni originali.
- La Control Room è autorevole per tenant, siti, enrollment e viste portfolio.
- Un Edge continua a monitorare in assenza di connettività e svuota l'outbox al ripristino.
- I dati Control Room non devono essere usati per comandare attuatori: questa release è read-only.

## Enrollment

Creare cliente, sito ed Edge dalla UI. Il token di enrollment viene mostrato una sola volta; copiarlo sul relativo Edge insieme a URL Control Room e segreto HMAC. Ogni installazione deve avere un `EM_EDGE_ID` UUID univoco.

## Dati

Il payload `schema_version: 1.0` include eventi normalizzati, inventario, versione, backlog e salute. La Control Room conserva i campioni raw per la finestra configurata e rollup al minuto più a lungo. Tenant e sito vengono applicati alle query sulla base dell'Edge autorizzato.

## Deployment

Usare `docker-compose.control-room.yml` con segreti forti, hostname DNS e backup PostgreSQL gestito dall'infrastruttura. Il certificato Caddy interno è adatto a una PKI controllata: per esposizione pubblica usare un dominio valido e una policy TLS concordata.
