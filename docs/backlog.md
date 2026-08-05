# Roadmap dopo la release 0.9

Le fondamenta P0–P5 sono implementate. Questa roadmap distingue ciò che è ancora necessario per una piattaforma commerciale su larga scala.

## P0 futuro — sicurezza prodotto

- credenziali individuali per Edge con rotazione e revoca senza token globale;
- MFA/SSO OIDC, sessioni revocabili e policy password configurabili;
- SBOM CycloneDX firmata, provenance immagini e release firmate;
- backup PostgreSQL cifrato, restore periodico e disaster recovery misurato;
- programma CVE e matrice versioni/aggiornamenti coerente con CRA.

## P1 futuro — affidabilità Control Room

- coda ingest dedicata per alta disponibilità e backpressure;
- aggregazioni 15 minuti, ora e giorno con ricostruzione deterministica;
- osservabilità OpenTelemetry, metriche Prometheus e alert sul servizio;
- isolamento tenant verificato con test di sicurezza dedicati;
- deployment orchestrato e replica database.

## P2 futuro — energia avanzata

- normalizzazione baseline automatica con gradi giorno, occupazione e produzione;
- versionamento e firma delle baseline da parte del professionista;
- import tariffe da fornitori, imposte e componenti non lineari;
- forecasting, peak shaving e ottimizzazione storage/ricarica;
- report ISO 50001/50006 con workflow di approvazione.

## P3 futuro — ecosistema dispositivi

- discovery SunSpec dinamica e scale factor runtime;
- BACnet/IP, MQTT, OPC UA e DLMS/COSEM;
- laboratorio hardware-in-the-loop e matrice firmware certificata;
- marketplace driver firmato e aggiornamenti controllati.

## P4 futuro — operazioni

- OTA firmato con canali, rollback e finestre di manutenzione;
- integrazione Tailscale reale o VPN enterprise equivalente;
- notifiche e escalation e-mail, SMS, webhook e app;
- app mobile/PWA offline e gestione multi-lingua completa.
