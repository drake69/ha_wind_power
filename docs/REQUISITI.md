# Requisiti — wind_power HACS Integration

## Obiettivo

L'integrazione serve a supportare una **decisione di acquisto**: installare o meno una turbina eolica residenziale. Per farlo, l'utente raccoglie misure dell'anemometro della propria stazione meteo (già integrata in Home Assistant) per un anno intero, e vuole sapere quanta energia ciascuno dei modelli di turbina che sta valutando *avrebbe* prodotto su quel periodo.

Non si tratta di misurare energia reale: la turbina non esiste ancora. Si tratta di una **simulazione retrospettiva continua** — man mano che i dati del vento si accumulano, l'integrazione ricalcola quanto avrebbe prodotto ogni modello candidato.

---

## Comportamento dell'integrazione

Ogni giorno (trigger periodico configurabile), l'integrazione:

1. Legge **tutta la storia disponibile** della velocità del vento dal recorder di Home Assistant, dall'inizio delle misurazioni.
2. Applica la **curva di potenza** di ciascun modello di turbina a ogni campione storico, tenendo conto di velocità di cut-in, velocità nominale e velocità di cut-out.
3. Integra la potenza nel tempo per ottenere l'**energia simulata totale** (kWh).
4. Calcola la **stima AEP** (Annual Energy Production) annualizzando l'energia simulata sui giorni effettivamente misurati.

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

Al momento dell'aggiunta dell'integrazione da HA → Dispositivi e servizi, l'utente configura:

- **Entity ID sensore vento** — il sensore di velocità dell'anemometro già presente in HA
- **Unità** — km/h oppure m/s
- **Densità aria** — kg/m³ (default 1.225, modificabile per altitudine/temperatura)

---

## Cosa l'integrazione NON fa

- Non misura energia reale prodotta da una turbina esistente.
- Non controlla inverter, caricabatterie o altri dispositivi.
- Non invia comandi o automazioni.
- Non mostra grafici propri: la visualizzazione storica è delegata ai tool nativi di HA (Energy dashboard, Grafana, ecc.).
