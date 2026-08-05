# Discovery Modbus TCP

La discovery assiste il tecnico durante la messa in servizio. Non sostituisce il progetto della rete, la documentazione del costruttore o la verifica sul quadro.

## Flusso operativo

1. Aprire **Impianto e dispositivi → Trova dispositivi**.
2. Inserire la subnet, normalmente `/24`, e le porte TCP da controllare.
3. Limitare l’intervallo Unit ID a quello effettivamente utilizzato.
4. Avviare la scansione e verificare gli endpoint che rispondono come Modbus.
5. Confrontare produttore, modello, variante di comunicazione e firmware con la targhetta.
6. Scegliere il profilo e assegnare un nome comprensibile nell’impianto.
7. Installare il dispositivo e controllare immediatamente qualità e coerenza delle misure live.

## Cosa viene rilevato

La scansione verifica prima l’apertura della porta TCP. Sugli endpoint raggiungibili prova Modbus Device Identification e, come fallback, una lettura FC03 di un solo registro. La risposta conferma la presenza dello slave; marca e modello sono disponibili soltanto se il dispositivo pubblica gli oggetti di identificazione.

La percentuale mostrata non è una certificazione del modello:

- `96%`: il testo del modello corrisponde a un profilo;
- `72%`: corrisponde il produttore;
- `35%`: è nota soltanto la compatibilità Modbus TCP.

## Limiti e protezioni

- reti IPv4 private RFC1918 soltanto;
- massimo 256 indirizzi per richiesta;
- massimo quattro porte e 32 Unit ID;
- massimo 32 endpoint TCP approfonditi per scansione e 12 probe contemporanei;
- timeout compreso fra 100 ms e 2 secondi;
- massimo cinque scansioni al minuto per client;
- operazioni Modbus esclusivamente read-only;
- accesso riservato ad amministratori e tecnici;
- ogni scansione e installazione viene registrata nell’audit log;
- hostname e indirizzi IP configurati vengono risolti per evitare duplicati.

La scansione genera comunque traffico sulla rete industriale. Concordare finestra, subnet e intervalli con il responsabile OT, soprattutto su gateway seriali, reti congestionate o apparati legacy.
