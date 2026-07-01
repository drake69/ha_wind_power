"""WhatIfWind sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_AIR_DENSITY,
    CONF_CUSTOM_TURBINES,
    CONF_WIND_ENTITY,
    CONF_WIND_UNIT,
    DOMAIN,
)
from .coordinator import WhatIfWindCoordinator
from .power import compute_power, energy_increment_kwh, to_ms
from .turbines import resolve_turbines

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WhatIfWindCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for turbine in resolve_turbines(entry.options.get(CONF_CUSTOM_TURBINES, [])):
        entities.append(WhatIfWindCurrentSensor(hass, entry, turbine))
        entities.append(WhatIfWindEnergySensor(hass, entry, turbine))
        entities.append(WhatIfWindAEPSensor(coordinator, entry, turbine))
        entities.append(WhatIfWindCapacityFactorSensor(coordinator, entry, turbine))

    async_add_entities(entities)

    # First refresh; errors must not block setup (historical data may be empty
    # on the very first start).
    await coordinator.async_config_entry_first_refresh()


def _device_info(entry: ConfigEntry, turbine: dict[str, Any]) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{turbine['id']}")},
        name=turbine["name"],
        manufacturer=turbine.get("manufacturer", "—"),
        model=turbine.get("model", "—"),
        entry_type=None,
    )


# ─── Instantaneous power ──────────────────────────────────────────────────────


class WhatIfWindCurrentSensor(SensorEntity):
    """
    Real-time estimated power (W).

    Updates every time the wind sensor state changes. Purely indicative: it
    shows how much the turbine would be producing right now with the current
    wind.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "current_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:wind-turbine"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, turbine: dict[str, Any]) -> None:
        self._hass = hass
        self._entry = entry
        self._turbine = turbine
        self._wind_entity_id: str = entry.data[CONF_WIND_ENTITY]
        self._wind_unit: str = entry.data[CONF_WIND_UNIT]
        self._air_density: float = entry.data[CONF_AIR_DENSITY]
        self._attr_unique_id = f"{entry.entry_id}_{turbine['id']}_power"
        self._attr_native_value: float | None = None
        self._attr_device_info = _device_info(entry, turbine)

    async def async_added_to_hass(self) -> None:
        # Initialize from the current value.
        state = self.hass.states.get(self._wind_entity_id)
        if state:
            self._update_from_wind_state(state.state)

        # Listen for future changes.
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._wind_entity_id],
                self._handle_wind_change,
            )
        )

    @callback
    def _handle_wind_change(self, event) -> None:
        new_state = event.data.get("new_state")
        if new_state:
            self._update_from_wind_state(new_state.state)
            self.async_write_ha_state()

    def _update_from_wind_state(self, raw_state: str) -> None:
        try:
            raw = float(raw_state)
        except (ValueError, TypeError):
            self._attr_native_value = None
            return
        wind_ms = to_ms(raw, self._wind_unit)
        self._attr_native_value = round(compute_power(self._turbine, wind_ms, self._air_density), 1)


# ─── Daily sensors (via coordinator) ──────────────────────────────────────────


class _DailyCoordinatorSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Base class for sensors updated once a day by the coordinator."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _turbine_data_key: str  # key in the dict returned by the coordinator

    def __init__(
        self,
        coordinator: WhatIfWindCoordinator,
        entry: ConfigEntry,
        turbine: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._turbine = turbine
        self._attr_device_info = _device_info(entry, turbine)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Restore the last known value to avoid "unavailable" after a restart.
        if last_state := await self.async_get_last_state():
            try:
                self._attr_native_value = float(last_state.state)
            except (ValueError, TypeError):
                pass

    @callback
    def _handle_coordinator_update(self) -> None:
        data: dict = self.coordinator.data or {}
        turbine_data = data.get(self._turbine["id"])
        if turbine_data:
            self._attr_native_value = turbine_data[self._turbine_data_key]
        self.async_write_ha_state()


class WhatIfWindEnergySensor(RestoreEntity, SensorEntity):
    """
    Estimated potential energy (kWh), integrated live from the wind sensor.

    Unlike the daily sensors below, this one does not read the coordinator: it
    accumulates its own running total on every wind change, using the same
    trapezoidal integration as the historical series. Two consequences:

      * it grows continuously (a new increment at each wind update), instead of
        moving once a day when the coordinator ticks;
      * it is monotonic by construction — every increment is ≥ 0 and the total is
        owned by the entity (restored across restarts via RestoreEntity), so it
        can never step backwards the way a coordinator re-seed could make it.

    This is NOT real energy: it is an estimate of how much energy this turbine
    *would* have produced at your site. That is why it does not expose
    `device_class=energy` and cannot be used as a meter in HA's energy
    dashboard.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "simulated_energy"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt-circle"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, turbine: dict[str, Any]) -> None:
        self._hass = hass
        self._entry = entry
        self._turbine = turbine
        self._wind_entity_id: str = entry.data[CONF_WIND_ENTITY]
        self._wind_unit: str = entry.data[CONF_WIND_UNIT]
        self._air_density: float = entry.data[CONF_AIR_DENSITY]
        self._attr_unique_id = f"{entry.entry_id}_{turbine['id']}_energy"
        self._attr_device_info = _device_info(entry, turbine)
        self._energy_kwh: float = 0.0
        self._prev_time = None
        self._prev_power_w: float = 0.0

    @property
    def native_value(self) -> float:
        return round(self._energy_kwh, 3)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Resume the running total from the last recorded value.
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._energy_kwh = float(last_state.state)
            except (ValueError, TypeError):
                pass

        # Seed the previous sample from the current wind so the first change
        # already produces an increment.
        if (state := self.hass.states.get(self._wind_entity_id)) is not None:
            self._set_prev(state.state, getattr(state, "last_changed", None))

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._wind_entity_id],
                self._handle_wind_change,
            )
        )

    def _set_prev(self, raw_state: str, when) -> None:
        try:
            raw = float(raw_state)
        except (ValueError, TypeError):
            self._prev_time = None
            self._prev_power_w = 0.0
            return
        self._prev_power_w = compute_power(
            self._turbine, to_ms(raw, self._wind_unit), self._air_density
        )
        self._prev_time = when

    @callback
    def _handle_wind_change(self, event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        try:
            raw = float(new_state.state)
        except (ValueError, TypeError):
            # Sensor went unavailable: break the interval so the gap is not
            # integrated once it comes back.
            self._prev_time = None
            self._prev_power_w = 0.0
            return

        power_w = compute_power(self._turbine, to_ms(raw, self._wind_unit), self._air_density)
        if self._prev_time is not None:
            dt_s = (new_state.last_changed - self._prev_time).total_seconds()
            self._energy_kwh += energy_increment_kwh(self._prev_power_w, power_w, dt_s)

        self._prev_time = new_state.last_changed
        self._prev_power_w = power_w
        self.async_write_ha_state()


class WhatIfWindAEPSensor(_DailyCoordinatorSensor):
    """
    Estimated AEP (kWh/year) — annualized projection of the simulated energy.

    Formula: simulated_energy_kwh / days_measured × 365.
    The estimate improves as the number of measured days grows.
    """

    _turbine_data_key = "aep_kwh"
    _attr_translation_key = "estimated_aep"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator, entry, turbine) -> None:
        super().__init__(coordinator, entry, turbine)
        self._attr_unique_id = f"{entry.entry_id}_{turbine['id']}_aep"
        self._attr_native_value: float | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = (self.coordinator.data or {}).get(self._turbine["id"], {})
        return {"days_measured": data.get("days_measured")}


class WhatIfWindCapacityFactorSensor(_DailyCoordinatorSensor):
    """
    Capacity factor (%) over the measured period.

    Ratio between the simulated energy and the theoretical maximum (turbine at
    rated power for the whole period). Indicates how usable the site's wind is
    for this model.
    """

    _turbine_data_key = "capacity_factor_pct"
    _attr_translation_key = "capacity_factor"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, entry, turbine) -> None:
        super().__init__(coordinator, entry, turbine)
        self._attr_unique_id = f"{entry.entry_id}_{turbine['id']}_capacity_factor"
        self._attr_native_value: float | None = None
