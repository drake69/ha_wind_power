DOMAIN = "wind_power"

CONF_WIND_ENTITY = "wind_entity_id"
CONF_WIND_UNIT = "wind_unit"
CONF_AIR_DENSITY = "air_density"

UNIT_MS = "ms"
UNIT_KMH = "kmh"
UNIT_MPH = "mph"
UNIT_KN = "kn"

# ─── Sorgente per popolare la serie giorno/mese/anno ──────────────────────────
# Due percorsi, stesso obiettivo (analisi 365 gg):
#   - influxdb: analisi retrospettiva, backfill all'indietro dallo storico loggato
#   - none:     parto dal logger e accumulo in avanti, la serie cresce nel tempo
CONF_BACKFILL_SOURCE = "backfill_source"
SOURCE_NONE = "none"
SOURCE_INFLUX = "influxdb"

# Parametri connessione InfluxDB (usati solo se backfill_source == influxdb).
# Lettura via HTTP API nativa (/api/v2/query, Flux) — nessuna libreria nel manifest.
CONF_INFLUX_URL = "influx_url"
CONF_INFLUX_TOKEN = "influx_token"
CONF_INFLUX_ORG = "influx_org"
CONF_INFLUX_BUCKET = "influx_bucket"
CONF_INFLUX_MEASUREMENT = "influx_measurement"
CONF_INFLUX_FIELD = "influx_field"

# Quanti giorni di storico richiedere al backfill retrospettivo.
BACKFILL_DAYS = 365

UPDATE_INTERVAL_HOURS = 24

# Scarta intervalli tra campioni consecutivi più lunghi di questa soglia:
# probabilmente il sensore era offline e non conosciamo il vento reale.
MAX_GAP_SECONDS = 7200  # 2 ore
