# Backlog post-MVP

Funzioni intenzionalmente non ampliate oltre il flusso verticale verificato:

- editor visuale completo del catalogo con griglia avanzata, undo/redo e gestione conflitti assistita;
- discovery Modbus guidata e scansione seriale con adattatori hardware reali;
- scheduler per fasce tariffarie, calendari produttivi e DSL KPI personalizzata;
- aggregazioni storiche/materialized view per flotte molto grandi;
- notifiche e-mail, SMS, webhook cliente e workflow di presa in carico allarmi;
- provider Tailscale reale con OAuth, approvazioni e revoche (l'interfaccia è presente, le mutazioni reali sono volutamente bloccate);
- gestione OTA, backup/restore, alta disponibilità Control Room e osservabilità distribuita;
- drag-and-drop visuale dell'albero (le API di spostamento e la protezione eliminazione sono già presenti);
- hardening produzione: secret manager, reverse proxy TLS, rate limiter distribuito, rotazione automatica token e SSO.

