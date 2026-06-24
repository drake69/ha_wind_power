"""DataUpdateCoordinator: legge la storia del vento e calcola le stime per turbina."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_AIR_DENSITY, CONF_WIND_ENTITY, CONF_WIND_UNIT, DOMAIN, UPDATE_INTERVAL_HOURS
from .power import compute_simulated_energy_kwh
from .turbines import TURBINE_CATALOG

_LOGGER = logging.getLogger(__name__)

# Data a sufficiente precedenza per catturare tutta la storia nel recorder
_HISTORY_START = datetime(2000, 1, 1, tzinfo=timezone.utc)


class WindPowerCoordinator(DataUpdateCoordinator):
    """
    Aggiornamento giornaliero: legge tutta la storia della velocità del vento
    dal recorder di HA e calcola, per ogni turbina nel catalogo:
      - energia_simulata_kwh
      - aep_kwh (proiezione annua)
      - capacity_factor_pct
      - days_measured
    """

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
        )
        self._wind_entity_id: str = entry.data[CONF_WIND_ENTITY]
        self._wind_unit: str = entry.data[CONF_WIND_UNIT]
        self._air_density: float = entry.data[CONF_AIR_DENSITY]

    async def _async_update_data(self) -> dict:
        states = await self._fetch_history()
        if not states:
            _LOGGER.debug("Nessuno stato storico trovato per %s", self._wind_entity_id)
            return {}

        first_ts = states[0].last_changed
        last_ts = states[-1].last_changed
        days_measured = max((last_ts - first_ts).total_seconds() / 86_400.0, 1.0)

        result: dict = {}
        for turbine in TURBINE_CATALOG:
            tid = turbine["id"]
            energy_kwh = compute_simulated_energy_kwh(
                states, turbine, self._air_density, self._wind_unit
            )
            aep_kwh = energy_kwh / days_measured * 365.0
            rated_w = turbine.get("rated_power_W", 0)
            if rated_w > 0:
                max_kwh = rated_w * days_measured * 24.0 / 1000.0
                capacity_factor = energy_kwh / max_kwh if max_kwh > 0 else 0.0
            else:
                capacity_factor = 0.0

            result[tid] = {
                "energy_kwh": round(energy_kwh, 3),
                "aep_kwh": round(aep_kwh, 1),
                "capacity_factor_pct": round(capacity_factor * 100.0, 1),
                "days_measured": round(days_measured, 1),
            }
            _LOGGER.debug(
                "%s: %.1f giorni, %.3f kWh simulati, AEP %.1f kWh/anno",
                turbine["name"], days_measured, energy_kwh, aep_kwh,
            )

        return result

    async def _fetch_history(self) -> list:
        """Esegue la query al recorder in un thread executor."""
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import get_significant_states
        except ImportError:
            _LOGGER.error("Il componente recorder non è disponibile")
            return []

        end_time = datetime.now(tz=timezone.utc)

        def _blocking_query():
            return get_significant_states(
                self.hass,
                _HISTORY_START,
                end_time,
                [self._wind_entity_id],
                filters=None,
                include_start_time_state=True,
                significant_changes_only=True,
                minimal_response=False,
                no_attributes=True,
            )

        try:
            states_map = await get_instance(self.hass).async_add_executor_job(_blocking_query)
        except Exception as err:
            _LOGGER.error("Errore lettura recorder: %s", err)
            return []

        return states_map.get(self._wind_entity_id, [])
