"""Config flow per Wind Power Estimator."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_AIR_DENSITY,
    CONF_WIND_ENTITY,
    CONF_WIND_UNIT,
    DOMAIN,
    UNIT_KMH,
    UNIT_MPH,
    UNIT_MS,
)


class WindPowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(
                title="Wind Power Estimator",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WIND_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required(CONF_WIND_UNIT, default=UNIT_KMH): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=UNIT_MS, label="m/s"),
                                selector.SelectOptionDict(value=UNIT_KMH, label="km/h"),
                                selector.SelectOptionDict(value=UNIT_MPH, label="mph"),
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Required(CONF_AIR_DENSITY, default=1.225): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.5, max=2.0, step=0.001, mode="box"
                        )
                    ),
                }
            ),
        )
