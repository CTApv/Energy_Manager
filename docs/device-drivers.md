# Catalogo driver dispositivi

I driver installabili dall'Edge vivono in `packages/modbus-catalog/profiles/drivers/`. La cartella è organizzata per funzione energetica e non per protocollo, così il tecnico trova il dispositivo come lo vede nell'impianto:

```text
drivers/
  multimeters/
    siemens-sentron-pac.yaml
    schneider-acti9-iem3000.yaml
  hybrid/
    huawei-sun2000-lb0-luna.yaml
  ev-chargers/
    abb-terra-ac.yaml
templates/
  generic-energy-assets.yaml
  generic-meter-v1.yaml
```

## Banco simulatori multi-dispositivo

La demo Docker avvia cinque slave indipendenti, tutti con Unit ID `1` salvo il multimetro che mantiene anche gli ID `1–4` per le prove di gerarchia:

| Categoria | Host dalla rete Docker | Porta dall’host | Profilo catalogo | Misure |
|---|---|---:|---|---:|
| Multimetro | `simulator:5020` | `5020` | `generic-meter-v1` | 57 |
| Inverter FV | `simulator-pv:5020` | `5021` | `generic-pv-inverter-v1` | 30 |
| Accumulo | `simulator-storage:5020` | `5022` | `generic-battery-storage-v1` | 28 |
| Colonnina EV | `simulator-ev:5020` | `5023` | `generic-ev-charger-v1` | 25 |
| Stazione meteo | `simulator-weather:5020` | `5024` | `generic-solar-sensor-v1` | 22 |

Ogni slave genera valori deterministici, coerenti con tipo, scala e unità del proprio profilo. L’endpoint HTTP di controllo usa le porte `18090–18094` e permette di attivare `anomaly` per verificare stati degradati e allarmi. Questi template servono esclusivamente per test e commissioning da banco.

## Regola di separazione

Creare un nuovo file quando cambia almeno uno di questi elementi:

- mappa registri o base indirizzi;
- codifica, byte order, word order o scale factor;
- sequenza/protocollo di comunicazione;
- compatibilità firmware che rende la lettura non intercambiabile;
- semantica o segno delle grandezze normalizzate.

Più modelli possono condividere un file solo se usano lo stesso driver e blocchi registro condivisibili. In quel caso ogni profilo mantiene il proprio `id`, mentre `driver.compatibility_group` e `driver.register_map` dichiarano esplicitamente la compatibilità.

## Metadati minimi del driver

```yaml
driver:
  implementation: standard_modbus
  compatibility_group: vendor-family-firmware
  register_map: vendor-map-revision
```

Il runtime aggiunge automaticamente `driver.source_file`. Due file non possono dichiarare lo stesso ID: il caricamento fallisce prima dell'avvio del polling. `templates/` contiene esempi generici e non deve essere usato su un cliente senza validazione della mappa reale.

## Inserimento di un nuovo modello

1. Copiare il driver di famiglia solo se la comunicazione è realmente compatibile; altrimenti creare un file nuovo.
2. Inserire esclusivamente funzioni Modbus di lettura e chiavi semantiche vendor-neutral.
3. Allegare manuale, revisione, data di verifica e limiti firmware.
4. Eseguire `pytest apps/api/tests/test_catalog.py apps/api/tests/test_driver_registry.py`.
5. Verificare durante il commissioning i valori contro display o portale del costruttore.

Questa struttura separa il catalogo dal polling generico: il motore di acquisizione rimane unico, mentre compatibilità, registri e normalizzazione evolvono per singolo driver.
