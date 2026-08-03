# Backlog post-MVP

Funzioni intenzionalmente non ampliate oltre il flusso verticale verificato:

- editor visuale completo del catalogo con griglia avanzata, undo/redo e gestione conflitti assistita;
- discovery Modbus guidata e scansione seriale con adattatori hardware reali;
- scheduler per fasce tariffarie, calendari produttivi e DSL KPI personalizzata;
- aggregazioni storiche/materialized view per flotte molto grandi;
- notifiche e-mail, SMS, webhook cliente e workflow di presa in carico allarmi;
- provider Tailscale reale con OAuth, approvazioni e revoche (l'interfaccia è presente, le mutazioni reali sono volutamente bloccate);
- gestione OTA, alta disponibilità Control Room e osservabilità distribuita; backup e ripristino Edge sono ora operativi con verifica d'integrità;
- editor catalogo avanzato con undo/redo; il drag-and-drop dell'albero energetico è ora disponibile;
- hardening avanzato: secret manager esterno, rate limiter distribuito, rotazione automatica token, aggiornamenti firmati e SSO. Il deployment Edge-only include già segreti obbligatori, TLS e checklist di commissioning.
