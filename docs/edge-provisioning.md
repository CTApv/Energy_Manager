# Provisioning Edge

## Modello operativo

Il provisioning distingue tre oggetti che non devono essere confusi:

1. la **rete dell'Edge** (schede Ethernet, indirizzi e DNS);
2. i **canali industriali** (politica TCP, bus seriali RTU o gateway RTU-over-TCP);
3. la **struttura energetica** (punto di consegna, quadri, reparti, linee e utenze).

Un dispositivo appartiene a un canale di comunicazione e viene collocato su un nodo dell'albero tramite una misura normalizzata. Il comando **Aggiungi dispositivo** svolge queste operazioni in un unico percorso guidato: modello/driver, indirizzamento coerente con il trasporto, posizione nell'albero e verifica finale. Il salvataggio è atomico, quindi un errore non lascia dispositivi senza posizione o associazioni incomplete.

## Regole di indirizzamento Modbus

| Trasporto | Configurato sul canale | Configurato sul dispositivo | Condivisione |
|---|---|---|---|
| Modbus TCP diretto | porta predefinita, timeout e retry | IP/hostname e porta | un endpoint e una sessione per dispositivo; Unit ID nascosto e gestito dal driver |
| Modbus RTU / RS485 | porta seriale, baud rate, parità e timeout | Unit ID | più dispositivi sullo stesso bus seriale |
| Modbus RTU-over-TCP | IP/porta del gateway, timeout e retry | Unit ID | più dispositivi dietro lo stesso gateway TCP |

La coppia IP/porta deve essere univoca tra i dispositivi TCP diretti. Lo Unit ID deve invece essere univoco soltanto all'interno del relativo bus RTU o gateway RTU-over-TCP.

Il pannello richiudibile **Contesto energetico**, disponibile sul lato destro di tutte le viste Edge, mostra l'albero monte-valle, i totali autorevoli, lo stato dei dispositivi e le priorità operative. Non sostituisce l'editor: è una vista live persistente che permette di passare rapidamente ai dati di dettaglio.

La modifica successiva della gerarchia resta disponibile nell'editor drag and drop. In questo modo il modello Siemens, o di qualunque altro costruttore, non modifica la semantica usata dalle dashboard.

## Dismissione sicura

Prima della rimozione l'API restituisce il numero di associazioni, campioni storici ed eventi di allarme coinvolti. La procedura richiede:

- una domanda di conferma;
- scelta esplicita tra conservazione dello storico e cancellazione irreversibile dei campioni.

Senza l'ultima scelta, i campioni restano nel database e il dispositivo assume lo stato `removed`, non viene più interrogato e non compare nella configurazione attiva. Tutta l'operazione viene registrata nell'audit log.

## Rete e porte seriali

L'inventario usa gli strumenti del sistema operativo quando disponibili e dispone di un fallback Linux per ambienti container minimali. Le porte seriali vengono rilevate tramite `pyserial` e, in fallback, dai device `/dev/ttyUSB*`, `/dev/ttyACM*`, `/dev/ttyAMA*` e `/dev/ttyS*`.

La dashboard salva profili DHCP o IPv4 statici con prefisso, gateway e DNS. L'applicazione all'host è deliberatamente separata: cambiare l'indirizzo dell'interfaccia in uso può interrompere il commissioning. Nei container standard la funzionalità host resta disabilitata; un installer autorizzato deve fornire il relativo servizio con privilegi minimi.
