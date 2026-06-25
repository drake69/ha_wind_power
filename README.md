# WhatIfWind

[![HACS Validation](https://github.com/drake69/WhatIfWind/actions/workflows/hacs.yml/badge.svg)](https://github.com/drake69/WhatIfWind/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/drake69/WhatIfWind/actions/workflows/hassfest.yml/badge.svg)](https://github.com/drake69/WhatIfWind/actions/workflows/hassfest.yml)
[![Tests](https://github.com/drake69/WhatIfWind/actions/workflows/tests.yml/badge.svg)](https://github.com/drake69/WhatIfWind/actions/workflows/tests.yml)

Home Assistant custom integration that answers a single question: **how much energy would a
wind turbine have produced at your site?**

It takes the wind-speed history of your own anemometer and runs it through the power curve of a
chosen turbine model, producing a retrospective estimate of the energy that turbine *would* have
generated — without installing any hardware.

## How it works

You point the integration at a local wind-speed sensor. The sensor captures the real conditions
of your specific site — hub height, nearby obstacles, terrain roughness — and WhatIfWind maps
each wind-speed reading onto the selected turbine's power curve to estimate production.

Two ways to build the 365-day series, same end result (daily / monthly / annual production):

- **InfluxDB → retrospective analysis.** If you already keep a local wind-data history in
  InfluxDB, the past 365 days are filled *backwards* and the chart is complete immediately.
- **Start now → forward fill.** With no prior history, the series is filled *forwards* from your
  logger and grows day by day until it covers a full year.

## Installation

### HACS (recommended)

1. In HACS, add this repository as a custom repository (category: *Integration*).
2. Install **WhatIfWind**.
3. Restart Home Assistant.

### Manual

Copy `custom_components/whatif_wind` into your Home Assistant `config/custom_components/`
directory and restart.

## Configuration

Add the integration from **Settings → Devices & Services → Add Integration → WhatIfWind**, then:

1. **Sensor & environment** — pick your wind-speed sensor and the air density for your site.
   The unit of measurement is auto-detected from the sensor; turbine models are loaded from the
   built-in catalog (`turbines.py`).
2. **Wind-speed unit** — only asked if the sensor doesn't expose a recognized unit.
3. **Historical data** — choose how the 365-day series gets filled (InfluxDB backfill or start now).
4. **InfluxDB connection** — if you chose InfluxDB: read-only access via the native HTTP API
   (Flux). Credentials are stored in the config entry; no extra libraries are installed.

## Dependencies

- Home Assistant `recorder` (used for the production history).
- Optional: an InfluxDB instance for retrospective backfill.

## Contributing

Issues and pull requests are welcome at
[github.com/drake69/WhatIfWind](https://github.com/drake69/WhatIfWind/issues).

## License

See the repository for license details.
