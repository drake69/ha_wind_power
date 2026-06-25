"""Config flow per Wind Power Estimator.

Albero dichiarativo: l'utente dichiara la propria situazione e l'integrazione
si auto-instrada verso uno dei due percorsi (stesso obiettivo: analisi 365 gg).

    user      → sensore vento, unità, densità aria
    history   → "Hai uno storico locale?"  (InfluxDB | parto da adesso)
    influxdb  → parametri di connessione   (solo se ho scelto InfluxDB)
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_AIR_DENSITY,
    CONF_BACKFILL_SOURCE,
    CONF_INFLUX_BUCKET,
    CONF_INFLUX_FIELD,
    CONF_INFLUX_MEASUREMENT,
    CONF_INFLUX_ORG,
    CONF_INFLUX_TOKEN,
    CONF_INFLUX_URL,
    CONF_WIND_ENTITY,
    CONF_WIND_UNIT,
    DOMAIN,
    SOURCE_INFLUX,
    SOURCE_NONE,
    UNIT_KMH,
    UNIT_KN,
    UNIT_MPH,
    UNIT_MS,
)
from .power import detect_internal_unit


class WindPowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        # Accumula i dati tra uno step e l'altro fino alla creazione dell'entry.
        self._data: dict = {}

    # ─── Step 1: fondamentali del sito turbina ────────────────────────────────
    async def async_step_user(self, user_input: dict | None = None):
        if user_input is not None:
            self._data.update(user_input)
            # L'unità la sa il sensore: la deduco da `unit_of_measurement`.
            state = self.hass.states.get(user_input[CONF_WIND_ENTITY])
            uom = state.attributes.get("unit_of_measurement") if state else None
            unit = detect_internal_unit(uom)
            if unit is not None:
                self._data[CONF_WIND_UNIT] = unit
                return await self.async_step_history()
            # Unità assente o non riconosciuta → la chiedo a mano.
            return await self.async_step_unit()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WIND_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required(CONF_AIR_DENSITY, default=1.225): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0.5, max=2.0, step=0.001, mode="box")
                    ),
                }
            ),
        )

    # ─── Step 1b: unità a mano (solo se non deducibile dal sensore) ────────────
    async def async_step_unit(self, user_input: dict | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_history()

        return self.async_show_form(
            step_id="unit",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WIND_UNIT, default=UNIT_KMH): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=UNIT_MS, label="m/s"),
                                selector.SelectOptionDict(value=UNIT_KMH, label="km/h"),
                                selector.SelectOptionDict(value=UNIT_MPH, label="mph"),
                                selector.SelectOptionDict(value=UNIT_KN, label="nodi (kn)"),
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    # ─── Step 2: dichiarazione situazione storico ─────────────────────────────
    async def async_step_history(self, user_input: dict | None = None):
        if user_input is not None:
            self._data.update(user_input)
            if user_input[CONF_BACKFILL_SOURCE] == SOURCE_INFLUX:
                return await self.async_step_influxdb()
            return self._create_entry()

        return self.async_show_form(
            step_id="history",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BACKFILL_SOURCE, default=SOURCE_NONE
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=SOURCE_INFLUX, label="Sì, in InfluxDB"
                                ),
                                selector.SelectOptionDict(
                                    value=SOURCE_NONE, label="No, parto da adesso"
                                ),
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    # ─── Step 3: connessione InfluxDB (condizionale) ──────────────────────────
    async def async_step_influxdb(self, user_input: dict | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return self._create_entry()

        return self.async_show_form(
            step_id="influxdb",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INFLUX_URL): selector.TextSelector(
                        selector.TextSelectorConfig(type="url")
                    ),
                    vol.Required(CONF_INFLUX_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(type="password")
                    ),
                    vol.Required(CONF_INFLUX_ORG): selector.TextSelector(),
                    vol.Required(CONF_INFLUX_BUCKET): selector.TextSelector(),
                    vol.Required(CONF_INFLUX_MEASUREMENT): selector.TextSelector(),
                    vol.Required(CONF_INFLUX_FIELD): selector.TextSelector(),
                }
            ),
        )

    def _create_entry(self):
        return self.async_create_entry(
            title="Wind Power Estimator",
            data=self._data,
        )
