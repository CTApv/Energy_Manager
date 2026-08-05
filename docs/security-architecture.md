# Architettura di sicurezza

## Confini di fiducia

L'Edge raccoglie e conserva localmente telemetria e configurazione. La Control Room è un concentratore opzionale multi-tenant: non è necessaria per il polling e non sostituisce l'autorità locale. Tra i due sistemi passa solo un contratto di sincronizzazione versionato.

```text
rete strumenti -> Edge -> HTTPS/HMAC -> Control Room -> browser autorizzato
                     |                    |
                  SQLite              PostgreSQL
```

Il traffico Modbus è considerato non autenticato e viene isolato nella rete tecnica. L'API e il browser sono un confine distinto. Internet e gli Edge remoti sono input non fidati per la Control Room.

## Controlli implementati

- password Argon2, JWT con scadenza e autorizzazione RBAC lato API;
- voci di menu filtrate per ruolo, senza affidarsi al solo frontend;
- token di enrollment mostrati una volta e conservati come hash;
- batch Edge firmati HMAC-SHA256 sul corpo canonico, autenticati anche con bearer token;
- idempotenza a livello batch ed evento e identità Edge UUID stabile;
- separazione delle rotte ammesse nei modi `edge` e `control-room`;
- CORS ristretto, CSP, anti-framing, `nosniff`, policy browser e HTTPS nel profilo cliente;
- profili Modbus validati e limitati alle funzioni di lettura;
- audit delle operazioni amministrative, retention differenziata e backup locale verificabile;
- scansioni delle dipendenze in CI e aggiornamenti mensili proposti da Dependabot.

## Modello di minaccia essenziale

| Minaccia | Mitigazione | Rischio residuo |
|---|---|---|
| replay o duplicazione batch | ID deterministico, marker batch/evento | la finestra temporale della firma non è ancora applicata |
| furto del segreto Edge | segreti univoci e rotazione tramite reenrollment | manca un vault integrato |
| spoofing Modbus | segmentazione OT e verifica commissioning | Modbus classico non autentica lo strumento |
| accesso UI non autorizzato | RBAC API, JWT e TLS | SSO/MFA non ancora disponibili |
| perdita telemetria durante outage | outbox persistente e retry | capacità limitata dallo storage Edge |
| dipendenza compromessa | lockfile, audit CI, aggiornamenti governati | serve una SBOM firmata per release |

## Secure development lifecycle

La struttura è predisposta a pratiche coerenti con IEC 62443-4-1: requisiti di sicurezza, revisione delle superfici esposte, test automatizzati, gestione vulnerabilità e documentazione delle assunzioni. Questo non costituisce certificazione IEC 62443 né dichiarazione di conformità al Cyber Resilience Act. Prima della commercializzazione sono necessari assessment, SBOM, politica aggiornamenti, gestione CVE e prove documentate sul prodotto distribuito.
