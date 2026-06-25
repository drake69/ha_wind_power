DOMAIN = "whatif_wind"

CONF_WIND_ENTITY = "wind_entity_id"
CONF_WIND_UNIT = "wind_unit"
CONF_AIR_DENSITY = "air_density"

UNIT_MS = "ms"
UNIT_KMH = "kmh"
UNIT_MPH = "mph"
UNIT_KN = "kn"

# ─── Source used to populate the daily/monthly/yearly series ───────────────────
# Two paths, same goal (365-day analysis):
#   - influxdb: retrospective analysis, back-filled from the logged history
#   - none:     start from the logger and accumulate forward, the series grows
CONF_BACKFILL_SOURCE = "backfill_source"
SOURCE_NONE = "none"
SOURCE_INFLUX = "influxdb"

# InfluxDB connection parameters (used only when backfill_source == influxdb).
# Read via the native HTTP API (/api/v2/query, Flux) — no library in the manifest.
CONF_INFLUX_URL = "influx_url"
CONF_INFLUX_TOKEN = "influx_token"
CONF_INFLUX_ORG = "influx_org"
CONF_INFLUX_BUCKET = "influx_bucket"
CONF_INFLUX_MEASUREMENT = "influx_measurement"
CONF_INFLUX_FIELD = "influx_field"

# How many days of history to request for the retrospective backfill.
BACKFILL_DAYS = 365

UPDATE_INTERVAL_HOURS = 24

# Discard intervals between consecutive samples longer than this threshold:
# the sensor was probably offline and we do not know the real wind.
MAX_GAP_SECONDS = 7200  # 2 hours

# ─── User-defined turbines (managed via the options flow) ──────────────────────
# Custom turbines are stored per config entry, in entry.options.
CONF_CUSTOM_TURBINES = "custom_turbines"

# Turbine form field keys (also the keys of the stored turbine dict).
CONF_T_NAME = "name"
CONF_T_SUBTYPE = "subtype"
CONF_T_BLADE_LENGTH = "blade_length_m"
CONF_T_DIAMETER = "diameter_m"
CONF_T_HEIGHT = "height_m"
CONF_T_RATED_POWER = "rated_power_W"
CONF_T_CP = "cp"
CONF_T_CUT_IN = "cut_in_ms"
CONF_T_CUT_OUT = "cut_out_ms"
CONF_T_POWER_CURVE = "power_curve"
CONF_T_REMOVE_IDS = "remove_ids"

# Turbine subtypes the user can pick. The subtype fixes the rotor axis (HAWT vs
# VAWT) and a sensible default power coefficient (Cp); the user only provides the
# geometry. Cp can still be overridden in the advanced fields.
SUBTYPE_HAWT_3BLADE = "hawt_3blade"
SUBTYPE_VAWT_SAVONIUS = "vawt_savonius"
SUBTYPE_VAWT_DARRIEUS = "vawt_darrieus"
SUBTYPE_VAWT_HROTOR = "vawt_hrotor"

SUBTYPE_TO_TYPE = {
    SUBTYPE_HAWT_3BLADE: "HAWT",
    SUBTYPE_VAWT_SAVONIUS: "VAWT",
    SUBTYPE_VAWT_DARRIEUS: "VAWT",
    SUBTYPE_VAWT_HROTOR: "VAWT",
}

# Default Cp per subtype (typical real-world values; the Betz limit is 0.593).
CP_DEFAULTS = {
    SUBTYPE_HAWT_3BLADE: 0.40,
    SUBTYPE_VAWT_SAVONIUS: 0.18,
    SUBTYPE_VAWT_DARRIEUS: 0.32,
    SUBTYPE_VAWT_HROTOR: 0.32,
}

# Defaults for the operational/loss parameters the user does not have to fill in.
DEFAULT_CUT_IN_MS = 3.0
DEFAULT_CUT_OUT_MS = 45.0
DEFAULT_LOSSES = {
    "kw": 0.03,  # wake
    "km": 0.005,  # mechanical
    "ke": 0.015,  # electrical
    "ke_t": 0.05,  # transmission
    "kt": 0.03,  # downtime
}

# Theoretical maximum power coefficient (Betz limit).
BETZ_LIMIT = 0.593
