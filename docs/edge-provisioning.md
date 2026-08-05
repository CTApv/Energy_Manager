# Provisioning Edge

## Modello operativo

Il provisioning distingue tre oggetti che non devono essere confusi:

1. la **rete dell'Edge** (schede Ethernet, indirizzi e DNS);
2. i **canali industriali** (endpoint Modbus TCP o bus seriali Modbus RTU);
3. la **struttura energetica** (punto di consegna, quadri, reparti, linee e utenze).

Un dispositivo appartiene a un canale di comunicazione e viene poi collocato su un nodo dell'albero tramite una misura normalizzata. In questo modo il modello Siemens, o di qualunque altro costruttore, non modifica la semantica usata dalle dashboard.

## Dismissione sicura

Prima della rimozione l'API restituisce il numero di associazioni, campioni storici ed eventi di allarme coinvolti. La procedura richiede:

- conferma testuale del nome del dispositivo;
- consenso esplicito alla rimozione delle associazioni, se presenti;
- scelta separata per l'eventuale cancellazione irreversibile dello storico.

Senza l'ultima scelta, i campioni restano nel database e il dispositivo assume lo stato `removed`, non viene più interrogato e non compare nella configurazione attiva. Tutta l'operazione viene registrata nell'audit log.

## Rete e porte seriali

L'inventario usa gli strumenti del sistema operativo quando disponibili e dispone di un fallback Linux per ambienti container minimali. Le porte seriali vengono rilevate tramite `pyserial` e, in fallback, dai device `/dev/ttyUSB*`, `/dev/ttyACM*`, `/dev/ttyAMA*` e `/dev/ttyS*`.

La dashboard salva profili DHCP o IPv4 statici con prefisso, gateway e DNS. L'applicazione all'host è deliberatamente separata: cambiare l'indirizzo dell'interfaccia in uso può interrompere il commissioning. Nei container standard la funzionalità host resta disabilitata; un installer autorizzato deve fornire il relativo servizio con privilegi minimi.
