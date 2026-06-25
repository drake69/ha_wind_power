"""DataUpdateCoordinator: feeds the *estimated* production history series.

Two paths, same goal (daily/monthly/yearly series over 365 days):
  - InfluxDB seed: retrospective backfill of the last year, complete at once;
  - logger accumulation: the series grows forward, one cycle at a time.

The state (cumulative totals + time cursor) is persisted in a Store, so the
accumulation resumes where it left off without recomputing history and without
depending on the recorder retention beyond the gap between two cycles.

The series lives as EXTERNAL statistics (see statistics.py): it is an estimate
of potential production, not real energy, and does not end up in the energy
dashboard.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    BACKFILL_DAYS,
    CONF_AIR_DENSITY,
    CONF_BACKFILL_SOURCE,
    CONF_CUSTOM_TURBINES,
    CONF_WIND_ENTITY,
    CONF_WIND_UNIT,
    DOMAIN,
    SOURCE_INFLUX,
    SOURCE_NONE,
    UPDATE_INTERVAL_HOURS,
)
from .statistics import (
    async_write_statistics,
    build_hourly_energy,
    statistic_id,
    to_cumulative,
)
from .turbines import resolve_turbines

_LOGGER = logging.getLogger(__name__)

_STORE_VERSION = 1


class WhatIfWindCoordinator(DataUpdateCoordinator):
    """Retrospective seed (InfluxDB) + forward accumulation (recorder)."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
        )
        self._entry = entry
        self._wind_entity_id: str = entry.data[CONF_WIND_ENTITY]
        self._wind_unit: str = entry.data[CONF_WIND_UNIT]
        self._air_density: float = entry.data[CONF_AIR_DENSITY]
        self._source: str = entry.data.get(CONF_BACKFILL_SOURCE, SOURCE_NONE)
        self._turbines = resolve_turbines(entry.options.get(CONF_CUSTOM_TURBINES, []))
        self._store = None
        self._state: dict | None = None

    # ─── State persistence ────────────────────────────────────────────────────
    async def _load_state(self) -> None:
        if self._state is not None:
            return
        if self._store is None:
            from homeassistant.helpers.storage import Store

            self._store = Store(self.hass, _STORE_VERSION, f"{DOMAIN}_{self._entry.entry_id}")
        stored = await self._store.async_load()
        self._state = stored or {
            "seeded": False,
            "start_ts": None,
            "last_processed_ts": None,
            "totals": {},
        }

    async def _save_state(self) -> None:
        if self._store is not None and self._state is not None:
            await self._store.async_save(self._state)

    # ─── Update cycle ─────────────────────────────────────────────────────────
    async def _async_update_data(self) -> dict:
        await self._load_state()
        now = datetime.now(tz=timezone.utc)

        if not self._state["seeded"]:
            await self._seed(now)

        await self._accumulate(now)
        await self._save_state()

        return self._build_result(now)

    async def _seed(self, now: datetime) -> None:
        """First population: backfill from InfluxDB if requested, otherwise zero."""
        seeded_from_influx = False
        if self._source == SOURCE_INFLUX:
            seeded_from_influx = await self._seed_from_influx()

        if not seeded_from_influx:
            # Start now and accumulate forward.
            self._state["start_ts"] = now.isoformat()
            self._state["last_processed_ts"] = now.isoformat()
            self._state["totals"] = {t["id"]: 0.0 for t in self._turbines}

        self._state["seeded"] = True

    async def _seed_from_influx(self) -> bool:
        from .influx import InfluxError, async_fetch_wind_samples

        try:
            samples = await async_fetch_wind_samples(self.hass, self._entry.data, BACKFILL_DAYS)
        except InfluxError as err:
            _LOGGER.error(
                "InfluxDB backfill failed: %s — falling back to forward accumulation", err
            )
            return False

        if not samples:
            _LOGGER.warning("InfluxDB returned no data — falling back to forward accumulation")
            return False

        totals: dict[str, float] = {}
        for turbine in self._turbines:
            hourly = build_hourly_energy(samples, turbine, self._air_density, self._wind_unit)
            cumulative = to_cumulative(hourly, 0.0)
            await async_write_statistics(
                self.hass,
                statistic_id(self._entry.entry_id, turbine["id"]),
                f"{turbine['name']} — Estimated production",
                cumulative,
            )
            totals[turbine["id"]] = cumulative[-1][1] if cumulative else 0.0

        self._state["start_ts"] = samples[0].last_changed.isoformat()
        self._state["last_processed_ts"] = samples[-1].last_changed.isoformat()
        self._state["totals"] = totals
        _LOGGER.info("InfluxDB backfill completed over %d samples", len(samples))
        return True

    async def _accumulate(self, now: datetime) -> None:
        """Extend the series forward with recorder data from the cursor to now."""
        last = _parse_ts(self._state["last_processed_ts"]) or now
        states = await self._fetch_history(last, now)
        if not states:
            return

        totals = self._state["totals"]
        for turbine in self._turbines:
            hourly = build_hourly_energy(states, turbine, self._air_density, self._wind_unit)
            if not hourly:
                continue
            base = totals.get(turbine["id"], 0.0)
            cumulative = to_cumulative(hourly, base)
            await async_write_statistics(
                self.hass,
                statistic_id(self._entry.entry_id, turbine["id"]),
                f"{turbine['name']} — Estimated production",
                cumulative,
            )
            totals[turbine["id"]] = cumulative[-1][1]

        self._state["last_processed_ts"] = states[-1].last_changed.isoformat()

    def _build_result(self, now: datetime) -> dict:
        """Summaries for the daily sensors (informational entities)."""
        start = _parse_ts(self._state["start_ts"]) or now
        days = max((now - start).total_seconds() / 86_400.0, 1.0)
        totals = self._state["totals"]

        result: dict = {}
        for turbine in self._turbines:
            energy = totals.get(turbine["id"], 0.0)
            aep = energy / days * 365.0
            rated_w = turbine.get("rated_power_W", 0)
            if rated_w > 0:
                max_kwh = rated_w * days * 24.0 / 1000.0
                cf = energy / max_kwh if max_kwh > 0 else 0.0
            else:
                cf = 0.0
            result[turbine["id"]] = {
                "energy_kwh": round(energy, 3),
                "aep_kwh": round(aep, 1),
                "capacity_factor_pct": round(cf * 100.0, 1),
                "days_measured": round(days, 1),
            }
        return result

    async def _fetch_history(self, start: datetime, end: datetime) -> list:
        """Query the recorder for the wind entity over [start, end]."""
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import get_significant_states
        except ImportError:
            _LOGGER.error("The recorder component is not available")
            return []

        def _blocking_query():
            return get_significant_states(
                self.hass,
                start,
                end,
                [self._wind_entity_id],
                filters=None,
                include_start_time_state=True,
                significant_changes_only=True,
                minimal_response=False,
                no_attributes=True,
            )

        try:
            states_map = await get_instance(self.hass).async_add_executor_job(_blocking_query)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Recorder read error: %s", err)
            return []

        return states_map.get(self._wind_entity_id, [])


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
