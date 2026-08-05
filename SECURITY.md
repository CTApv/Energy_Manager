# Security policy

## Versioni supportate

La linea `0.9.x` riceve correzioni di sicurezza. Le versioni precedenti sono da aggiornare prima del commissioning.

## Segnalazione responsabile

Non aprire issue pubbliche con exploit, credenziali, indirizzi di impianto o dati cliente. Inviare una descrizione riservata a [filippoctass@gmail.com](mailto:filippoctass@gmail.com), includendo versione, impatto, prerequisiti e una riproduzione minima priva di dati personali.

La presa in carico è prevista entro 3 giorni lavorativi. La severità, il piano di mitigazione e la finestra di pubblicazione vengono concordati con il segnalante. Non è promesso un programma di ricompense.

## Confini di sicurezza

- I driver Modbus distribuiti sono in sola lettura; qualsiasi estensione con scritture richiede una revisione separata.
- Il deployment di produzione richiede segreti univoci, HTTPS e un `EM_EDGE_ID` distinto per ogni Edge.
- La gestione di rete host resta disabilitata per impostazione predefinita.
- Token, file `.env`, backup e database di clienti non devono essere allegati a issue o commit.

La procedura tecnica e i rischi residui sono descritti in [docs/security-architecture.md](docs/security-architecture.md).
