# Requisiti — wind_power HACS Integration

## Obiettivo

L'integrazione serve a supportare una **decisione di acquisto**: installare o meno una turbina eolica residenziale. Per farlo, l'utente raccoglie misure dell'anemometro della propria stazione meteo (già integrata in Home Assistant) per un anno intero, e vuole sapere quanta energia ciascuno dei modelli di turbina che sta valutando *avrebbe* prodotto su quel periodo.

Non si tratta di misurare energia reale: la turbina non esiste ancora. Si tratta di una **simulazione retrospettiva continua** — man mano che i dati del vento si accumulano, l'integrazione ricalcola quanto avrebbe prodotto ogni modello candidato.

---

## Comportamento dell'integrazione

L'obiettivo è una **serie di produzione stimata giorno/mese/anno** su 365 giorni.
Due percorsi alimentano la *stessa* serie (scelti nel config flow):

- **Ho lo storico (InfluxDB)** → *analisi retrospettiva*: l'integrazione legge fino a
  365 giorni di vento da InfluxDB e riempie la serie **all'indietro**, completa da subito.
- **Non ho pregressi** → *accumulo in avanti*: parte dal logger e, a ogni ciclo, estende
  la serie con i nuovi dati del recorder; il quadro annuale si completa nel tempo.

La serie vive come **long-term statistics esterne** di HA (`wind_power:…`): compatte
(una riga per ora), aggregate automaticamente ora→giorno→mese→anno, e popolabili sia
retrodatate (backfill) sia in append. Uno **Store** persiste il cursore temporale e i
totali cumulativi, così l'accumulo riprende senza ricalcolare la storia e senza
dipendere dalla retention del recorder oltre il gap fra due cicli.

Ogni ciclo, per ciascun modello di turbina, l'integrazione:

1. Applica la **curva di potenza** a ogni campione (cut-in / nominale / cut-out).
2. Integra la potenza **a livello orario** e somma le ore (mai mediare il vento a
   livello giornaliero e poi elevare al cubo: la potenza va come `v³`, convessa, e si
   sottostimerebbe).
3. Aggiorna la serie statistics e i totali cumulativi.
4. Calcola la **stima AEP** annualizzando l'energia stimata sui giorni coperti.

> ⚠️ È una **stima di produzione potenziale, non energia reale**. Per questo i sensori
> in kWh non espongono `device_class=energy` e la serie non è un contatore: **non va
> nella dashboard energia di HA**.

---

## Sensori prodotti

Per ogni modello di turbina nel catalogo, l'integrazione espone i seguenti sensori:

| Sensore | Unità | Significato |
|---------|-------|-------------|
| `energia_simulata_kwh` | kWh | Energia totale che la turbina *avrebbe* prodotto dall'inizio delle misurazioni |
| `aep_stimato_kwh` | kWh/anno | Proiezione annua: `energia_simulata / giorni_misurati × 365` |
| `potenza_attuale_w` | W | Potenza istantanea con il vento corrente (orientativa, aggiornata in tempo reale) |
| `capacity_factor_pct` | % | Rapporto tra energia simulata e massimo teorico nel periodo |

Il sensore `potenza_attuale_w` è l'unico aggiornato in tempo reale (quando cambia lo stato del sensore vento). Gli altri tre vengono aggiornati una volta al giorno.

---

## Catalogo turbine

L'integrazione include un catalogo di modelli di turbina definito in `turbines.py`. Ogni modello specifica:

- Nome, produttore e tipo (vedi sotto)
- Geometria specifica per tipo (vedi sotto)
- Potenza nominale (W)
- Velocità di cut-in, nominale e cut-out (m/s)
- Modalità di calcolo della potenza:
  - **Parametrica**: Cp (coefficiente di potenza) e coefficienti di perdita (meccaniche, elettriche, trasmissione, downtime)
  - **Tabulare**: tabella `[velocità_ms, potenza_W]` fornita dal produttore, con interpolazione lineare tra i punti

I modelli di esempio includi sono tre (VAWT Savonius 500 W, HAWT 1 kW, VAWT Darrieus H-rotor 2 kW). L'utente sostituisce o integra questi con i modelli reali che sta valutando modificando `turbines.py`.

### Tipi di turbina supportati

Il tipo determina la formula con cui viene calcolata l'area spazzata, che è il parametro geometrico fondamentale della stima di potenza. I sottotipi di una stessa categoria condividono la stessa formula d'area: le differenze di efficienza tra sottotipi sono interamente catturate dal coefficiente Cp (in modalità parametrica) o dalla curva di potenza (in modalità tabulare).

| Tipo | Sottotipi tipici (scala residenziale) | Area spazzata | Cp tipico |
|------|---------------------------------------|---------------|-----------|
| **HAWT** — asse orizzontale | Bipala, tripala (upwind o downwind) | `π × r²` (r = lunghezza pala) | 0.35 – 0.45 |
| **VAWT** — asse verticale | Darrieus (a uovo), H-rotor/Giromill (pale dritte), Savonius (a cucchiaio), elicoidale | `diametro × altezza` | 0.12 – 0.40 |

I Savonius sono a trascinamento (drag-based): Cp basso (~0.15–0.20) ma cut-in molto basso (~1–2 m/s), adatti a venti deboli e irregolari. I Darrieus/H-rotor sono a portanza (lift-based): Cp più alto (~0.30–0.40), cut-in ~3 m/s, più simili in efficienza agli HAWT. Gli HAWT tripala sono generalmente i più efficienti ma richiedono orientamento attivo verso il vento.

---

## Configurazione (config flow HA)

Config flow a step, dichiarativo e informativo:

1. **`user`** — Entity ID sensore vento + densità aria (kg/m³, default 1.225). L'**unità**
   viene **dedotta** dall'attributo `unit_of_measurement` del sensore (m/s, km/h, mph, kn).
2. **`unit`** *(solo fallback)* — appare **solo** se HA non espone un'unità riconosciuta:
   l'utente la sceglie a mano.
3. **`history`** — «Hai uno storico locale?»: *Sì, in InfluxDB* → analisi retrospettiva;
   *No, parto da adesso* → accumulo in avanti.
4. **`influxdb`** *(solo se InfluxDB)* — URL, token, org, bucket, measurement, field.
   Lettura via HTTP API nativa (Flux), nessuna libreria aggiuntiva installata.

Alla rimozione dell'integrazione (`async_remove_entry`) la pulizia è completa: le
statistics esterne e lo Store vengono cancellati, niente dati orfani.

---

## Cosa l'integrazione NON fa

- Non misura energia reale prodotta da una turbina esistente.
- Non alimenta la **dashboard energia** di HA: la produzione è stimata, non reale.
- Non controlla inverter, caricabatterie o altri dispositivi.
- Non invia comandi o automazioni.
- Non mostra grafici propri: la serie giorno/mese/anno è esposta come long-term
  statistics, da visualizzare con la **Statistics Graph card**, ApexCharts o Grafana.
