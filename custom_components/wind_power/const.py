DOMAIN = "wind_power"

CONF_WIND_ENTITY = "wind_entity_id"
CONF_WIND_UNIT = "wind_unit"
CONF_AIR_DENSITY = "air_density"

UNIT_MS = "ms"
UNIT_KMH = "kmh"
UNIT_MPH = "mph"

UPDATE_INTERVAL_HOURS = 24

# Scarta intervalli tra campioni consecutivi più lunghi di questa soglia:
# probabilmente il sensore era offline e non conosciamo il vento reale.
MAX_GAP_SECONDS = 7200  # 2 ore
