# Commissioning di un Edge cliente

Questa procedura porta un nuovo IPC da macchina vuota a Edge consegnabile. Il report nell'app verifica la configurazione software; non sostituisce prove elettriche, verifiche metrologiche, cybersecurity assessment del sito o verbali contrattuali.

## 1. Prerequisiti del sito

- IPC Linux AMD64 o ARM64 con Docker Engine e Compose aggiornati;
- IP statico o prenotazione DHCP, hostname DNS locale e sincronizzazione NTP;
- VLAN OT concordata, con accesso in uscita disabilitabile se l'Edge resta stand-alone;
- porte Modbus raggiungibili soltanto dall'Edge: non pubblicare TCP/502 verso LAN utente, Internet o tailnet;
- per RTU, adattatore RS485 isolato e identificatore stabile `/dev/serial/by-id/...` preferito a `/dev/ttyUSB0`;
- UPS dimensionato per IPC, switch e gateway essenziali.

## 2. Preparazione sicura

```powershell
.\scripts\new-customer-env.ps1 -Hostname energy-manager.cliente.local
New-Item -ItemType Directory -Force data | Out-Null
docker compose -f docker-compose.edge.yml config --quiet
docker compose -f docker-compose.edge.yml up -d --build
```

Per un bus RTU aggiungere l'overlay e impostare `EM_RTU_DEVICE` con il percorso stabile del dispositivo:

```bash
docker compose -f docker-compose.edge.yml -f docker-compose.rtu.yml up -d --build
```

Il gateway Caddy espone solo HTTPS e usa una CA locale. Distribuire la root CA ai soli terminali autorizzati, oppure integrare la PKI del cliente. Non ignorare gli avvisi TLS durante la consegna.

## 3. Configurazione nell'app

1. accedere come `admin` usando la password generata nel file `.env`;
2. creare un secondo amministratore nominativo e gli account operatore/viewer;
3. impostare la denominazione reale del sito;
4. aggiungere le connessioni TCP o RTU con timeout conservativo e retry zero nella prima diagnosi;
5. usare **Struttura impianto → Aggiungi dispositivo**, verificando modello e variante; inserire IP/porta sul dispositivo per TCP diretto oppure lo Unit ID per RTU e RTU-over-TCP;
6. scegliere durante la stessa procedura il nodo energetico esistente oppure crearne uno nel corretto ramo monte/valle;
7. verificare l'esito del primo polling e confrontare tensioni, correnti, potenza ed energia con il display dello strumento;
8. verificare byte/word order, rapporti TA/TV e unità sul manuale della specifica variante firmware;
9. rifinire la gerarchia con il drag and drop, associando prima il generale e poi le utenze a valle;
10. configurare e provare soglie, presa visione e rientro;
11. aprire **Sistema → Commissioning**, risolvere tutti i controlli bloccanti e creare il backup finale.

## 4. Site Acceptance Test

Registrare almeno:

- inventario IPC, adattatori, gateway e strumenti con seriale/firmware;
- schema rete e RS485, terminazioni e polarizzazione;
- tabella endpoint TCP per dispositivo, bus/gateway condivisi, Unit ID RTU e profili catalogo/versioni;
- confronto di almeno cinque misure live per ogni modello;
- perdita comunicazione e riconnessione senza riavvio dell'Edge;
- continuità con Control Room e Internet scollegati;
- correttezza del bilancio monte/valle e del segno import/export;
- apertura e chiusura di un allarme di prova;
- riavvio controllato dell'IPC e ripartenza automatica dei container;
- backup scaricato, hash SHA-256 conservato e restore provato fuori produzione.

## 5. Backup e ripristino

L'Edge crea backup consistenti tramite l'API SQLite, esegue `integrity_check`, salva un manifest SHA-256 e conserva il numero configurato. Copiare periodicamente un backup fuori dall'IPC.

```bash
./scripts/restore-edge.sh --confirm data/backups/energy-manager-edge-YYYYMMDDTHHMMSSZ.db
```

Il ripristino è offline e conserva una copia del database corrente. Va provato prima su un clone, mai per la prima volta sul sistema produttivo.

## 6. Criterio di consegna

- il report Commissioning riporta `ready`;
- non esistono dispositivi `offline` o `degraded` senza deroga firmata;
- il cliente ha ricevuto account nominativi, URL, matrice ruoli e procedura di escalation;
- segreti e backup non sono nel repository né nella documentazione condivisa;
- sono definiti responsabile aggiornamenti, finestra di manutenzione e conservazione dati.

## Riferimenti di governance

L'applicabilità va valutata con i responsabili legali e cybersecurity del cliente. Fonti primarie:

- [Direttiva NIS2 (UE) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)
- [Cyber Resilience Act, Regolamento (UE) 2024/2847](https://eur-lex.europa.eu/eli/reg/2024/2847/oj)
- [EU Data Act, Regolamento (UE) 2023/2854](https://eur-lex.europa.eu/eli/reg/2023/2854/oj)
- [serie IEC 62443 per sistemi IACS](https://www.iec.ch/cyber-security)

Il Data Act è applicabile dal 12 settembre 2025. Per il CRA, il capitolo sugli organismi di valutazione si applica dall'11 giugno 2026, il reporting dall'11 settembre 2026 e l'applicazione generale dall'11 dicembre 2027. Queste date non determinano da sole l'applicabilità al prodotto o al cliente.
