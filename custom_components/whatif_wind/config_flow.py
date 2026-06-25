"""Config flow for WhatIfWind.

Declarative tree: the user describes their situation and the integration routes
itself to one of the two paths (same goal: 365-day analysis).

    user      → wind sensor, unit, air density
    history   → "Do you have a local history?"  (InfluxDB | start now)
    influxdb  → connection parameters            (only if InfluxDB was chosen)

Turbines are not configured here: they are added afterwards from the options
flow (the "Configure" button on the integration).
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    BETZ_LIMIT,
    CONF_AIR_DENSITY,
    CONF_BACKFILL_SOURCE,
    CONF_CUSTOM_TURBINES,
    CONF_INFLUX_BUCKET,
    CONF_INFLUX_FIELD,
    CONF_INFLUX_MEASUREMENT,
    CONF_INFLUX_ORG,
    CONF_INFLUX_TOKEN,
    CONF_INFLUX_URL,
    CONF_T_BLADE_LENGTH,
    CONF_T_CP,
    CONF_T_CUT_IN,
    CONF_T_CUT_OUT,
    CONF_T_DIAMETER,
    CONF_T_HEIGHT,
    CONF_T_NAME,
    CONF_T_POWER_CURVE,
    CONF_T_RATED_POWER,
    CONF_T_REMOVE_IDS,
    CONF_T_SUBTYPE,
    CONF_WIND_ENTITY,
    CONF_WIND_UNIT,
    CP_DEFAULTS,
    DEFAULT_CUT_IN_MS,
    DEFAULT_CUT_OUT_MS,
    DOMAIN,
    SOURCE_INFLUX,
    SOURCE_NONE,
    SUBTYPE_HAWT_3BLADE,
    SUBTYPE_TO_TYPE,
    SUBTYPE_VAWT_DARRIEUS,
    SUBTYPE_VAWT_HROTOR,
    SUBTYPE_VAWT_SAVONIUS,
    UNIT_KMH,
    UNIT_KN,
    UNIT_MPH,
    UNIT_MS,
)
from .power import detect_internal_unit
from .turbines import build_turbine


class WhatIfWindConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        # Accumulates data across steps until the entry is created.
        self._data: dict = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return WhatIfWindOptionsFlow()

    # ─── Step 1: turbine-site fundamentals ────────────────────────────────────
    async def async_step_user(self, user_input: dict | None = None):
        if user_input is not None:
            self._data.update(user_input)
            # The sensor knows the unit: derive it from `unit_of_measurement`.
            state = self.hass.states.get(user_input[CONF_WIND_ENTITY])
            uom = state.attributes.get("unit_of_measurement") if state else None
            unit = detect_internal_unit(uom)
            if unit is not None:
                self._data[CONF_WIND_UNIT] = unit
                return await self.async_step_history()
            # Unit absent or unrecognized → ask for it manually.
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

    # ─── Step 1b: unit by hand (only if not derivable from the sensor) ─────────
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
                                selector.SelectOptionDict(value=UNIT_KN, label="knots (kn)"),
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    # ─── Step 2: history situation ────────────────────────────────────────────
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
                                    value=SOURCE_INFLUX, label="Yes, in InfluxDB"
                                ),
                                selector.SelectOptionDict(value=SOURCE_NONE, label="No, start now"),
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    # ─── Step 3: InfluxDB connection (conditional) ────────────────────────────
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
            title="WhatIfWind",
            data=self._data,
        )


class WhatIfWindOptionsFlow(config_entries.OptionsFlow):
    """Manage user-defined turbines after setup (add / remove)."""

    def __init__(self) -> None:
        self._new: dict = {}

    @property
    def _customs(self) -> list[dict]:
        return list(self.config_entry.options.get(CONF_CUSTOM_TURBINES, []))

    async def async_step_init(self, user_input: dict | None = None):
        return self.async_show_menu(step_id="init", menu_options=["add", "remove"])

    # ─── Add: step A — name + subtype ─────────────────────────────────────────
    async def async_step_add(self, user_input: dict | None = None):
        if user_input is not None:
            self._new = dict(user_input)
            return await self.async_step_add_geometry()

        return self.async_show_form(
            step_id="add",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_T_NAME): selector.TextSelector(),
                    vol.Required(
                        CONF_T_SUBTYPE, default=SUBTYPE_HAWT_3BLADE
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=SUBTYPE_HAWT_3BLADE,
                                    label="HAWT — 3 blades (horizontal axis)",
                                ),
                                selector.SelectOptionDict(
                                    value=SUBTYPE_VAWT_SAVONIUS,
                                    label="VAWT — Savonius (vertical axis)",
                                ),
                                selector.SelectOptionDict(
                                    value=SUBTYPE_VAWT_DARRIEUS,
                                    label="VAWT — Darrieus (vertical axis)",
                                ),
                                selector.SelectOptionDict(
                                    value=SUBTYPE_VAWT_HROTOR,
                                    label="VAWT — H-rotor / Giromill (vertical axis)",
                                ),
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    # ─── Add: step B — geometry + nameplate (+ advanced) ──────────────────────
    async def async_step_add_geometry(self, user_input: dict | None = None):
        subtype = self._new.get(CONF_T_SUBTYPE, SUBTYPE_HAWT_3BLADE)
        is_hawt = SUBTYPE_TO_TYPE.get(subtype) == "HAWT"

        if user_input is not None:
            try:
                turbine = build_turbine(
                    {**self._new, **user_input},
                    existing_ids={t["id"] for t in self._customs},
                )
            except ValueError:
                return self._geometry_form(is_hawt, subtype, errors={"base": "invalid_turbine"})
            return self.async_create_entry(
                title="", data={CONF_CUSTOM_TURBINES: [*self._customs, turbine]}
            )

        return self._geometry_form(is_hawt, subtype)

    def _geometry_form(self, is_hawt: bool, subtype: str, errors: dict | None = None):
        length = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.05, max=100, step=0.01, mode="box", unit_of_measurement="m"
            )
        )
        fields: dict = {}
        if is_hawt:
            fields[vol.Required(CONF_T_BLADE_LENGTH)] = length
        else:
            fields[vol.Required(CONF_T_DIAMETER)] = length
            fields[vol.Required(CONF_T_HEIGHT)] = length
        fields[vol.Required(CONF_T_RATED_POWER)] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=1_000_000, step=1, mode="box")
        )
        # Advanced (pre-filled defaults; the user rarely needs to touch these).
        fields[vol.Optional(CONF_T_CP, default=CP_DEFAULTS[subtype])] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=0.01, max=BETZ_LIMIT, step=0.001, mode="box")
        )
        fields[vol.Optional(CONF_T_CUT_IN, default=DEFAULT_CUT_IN_MS)] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=30, step=0.1, mode="box")
        )
        fields[vol.Optional(CONF_T_CUT_OUT, default=DEFAULT_CUT_OUT_MS)] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=100, step=0.1, mode="box")
        )
        fields[vol.Optional(CONF_T_POWER_CURVE, default="")] = selector.TextSelector(
            selector.TextSelectorConfig(multiline=True)
        )
        return self.async_show_form(
            step_id="add_geometry",
            data_schema=vol.Schema(fields),
            errors=errors or {},
        )

    # ─── Remove ───────────────────────────────────────────────────────────────
    async def async_step_remove(self, user_input: dict | None = None):
        customs = self._customs
        if not customs:
            return self.async_abort(reason="no_custom_turbines")

        if user_input is not None:
            to_remove = set(user_input[CONF_T_REMOVE_IDS])
            kept = [t for t in customs if t["id"] not in to_remove]
            return self.async_create_entry(title="", data={CONF_CUSTOM_TURBINES: kept})

        return self.async_show_form(
            step_id="remove",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_T_REMOVE_IDS): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=t["id"], label=t["name"])
                                for t in customs
                            ],
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )
