"""Sensori Wind Power Estimator."""

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

from .const import CONF_AIR_DENSITY, CONF_WIND_ENTITY, CONF_WIND_UNIT, DOMAIN
from .coordinator import WindPowerCoordinator
from .power import compute_power, to_ms
from .turbines import TURBINE_CATALOG

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WindPowerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for turbine in TURBINE_CATALOG:
        entities.append(WindPowerCurrentSensor(hass, entry, turbine))
        entities.append(WindPowerEnergySensor(coordinator, entry, turbine))
        entities.append(WindPowerAEPSensor(coordinator, entry, turbine))
        entities.append(WindPowerCapacityFactorSensor(coordinator, entry, turbine))

    async_add_entities(entities)

    # Primo aggiornamento; errori non bloccano il setup (dati storici potrebbero
    # essere vuoti al primo avvio)
    await coordinator.async_config_entry_first_refresh()


def _device_info(entry: ConfigEntry, turbine: dict[str, Any]) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{turbine['id']}")},
        name=turbine["name"],
        manufacturer=turbine.get("manufacturer", "—"),
        model=turbine.get("model", "—"),
        entry_type=None,
    )


# ─── Potenza istantanea ──────────────────────────────────────────────────────


class WindPowerCurrentSensor(SensorEntity):
    """
    Potenza stimata in tempo reale (W).

    Si aggiorna ogni volta che cambia lo stato del sensore vento.
    Valore puramente orientativo: mostra quanto starebbe producendo
    la turbina in questo momento con il vento corrente.
    """

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
        self._attr_name = f"{turbine['name']} — Potenza attuale"
        self._attr_native_value: float | None = None
        self._attr_device_info = _device_info(entry, turbine)

    async def async_added_to_hass(self) -> None:
        # Inizializza dal valore corrente
        state = self.hass.states.get(self._wind_entity_id)
        if state:
            self._update_from_wind_state(state.state)

        # Ascolta i cambiamenti futuri
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


# ─── Sensori giornalieri (via coordinator) ───────────────────────────────────


class _DailyCoordinatorSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Base per i sensori aggiornati una volta al giorno dal coordinator."""

    _attr_should_poll = False
    _turbine_data_key: str  # chiave nel dict restituito dal coordinator

    def __init__(
        self,
        coordinator: WindPowerCoordinator,
        entry: ConfigEntry,
        turbine: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._turbine = turbine
        self._attr_device_info = _device_info(entry, turbine)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Ripristina l'ultimo valore noto per evitare "unavailable" al riavvio
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


class WindPowerEnergySensor(_DailyCoordinatorSensor):
    """
    Energia potenziale stimata (kWh) sul periodo coperto dai dati di vento.

    NON è energia reale: è una valutazione di quanta energia *avrebbe* prodotto
    questa turbina sul tuo sito. Per questo non espone `device_class=energy` e
    non è candidabile come contatore nella dashboard energia di HA.
    """

    _turbine_data_key = "energy_kwh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt-circle"

    def __init__(self, coordinator, entry, turbine) -> None:
        super().__init__(coordinator, entry, turbine)
        self._attr_unique_id = f"{entry.entry_id}_{turbine['id']}_energy"
        self._attr_name = f"{turbine['name']} — Energia simulata"
        self._attr_native_value: float | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = (self.coordinator.data or {}).get(self._turbine["id"], {})
        return {"giorni_misurati": data.get("days_measured")}


class WindPowerAEPSensor(_DailyCoordinatorSensor):
    """
    AEP stimato (kWh/anno) — proiezione annua dell'energia simulata.

    Formula: energia_simulata_kwh / giorni_misurati × 365.
    La stima migliora all'aumentare dei giorni di misurazione.
    """

    _turbine_data_key = "aep_kwh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator, entry, turbine) -> None:
        super().__init__(coordinator, entry, turbine)
        self._attr_unique_id = f"{entry.entry_id}_{turbine['id']}_aep"
        self._attr_name = f"{turbine['name']} — AEP stimato"
        self._attr_native_value: float | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = (self.coordinator.data or {}).get(self._turbine["id"], {})
        return {"giorni_misurati": data.get("days_measured")}


class WindPowerCapacityFactorSensor(_DailyCoordinatorSensor):
    """
    Capacity factor (%) nel periodo misurato.

    Rapporto tra energia simulata e massimo teorico (turbina alla potenza
    nominale per tutta la durata del periodo). Indica quanto è sfruttabile
    il vento del sito per questo modello.
    """

    _turbine_data_key = "capacity_factor_pct"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, entry, turbine) -> None:
        super().__init__(coordinator, entry, turbine)
        self._attr_unique_id = f"{entry.entry_id}_{turbine['id']}_capacity_factor"
        self._attr_name = f"{turbine['name']} — Capacity factor"
        self._attr_native_value: float | None = None
