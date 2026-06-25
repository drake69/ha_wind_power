"""Wind Power Estimator — HACS integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import WindPowerCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = WindPowerCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Disinstallazione pulita: rimuove statistics esterne e stato persistito.

    Le statistics e lo Store sopravvivono all'unload (vivono nel recorder e in
    .storage): senza questa pulizia resterebbero orfani dopo la rimozione.
    """
    from homeassistant.helpers.storage import Store

    from .statistics import async_clear_statistics, statistic_id
    from .turbines import TURBINE_CATALOG

    stat_ids = [statistic_id(entry.entry_id, t["id"]) for t in TURBINE_CATALOG]
    await async_clear_statistics(hass, stat_ids)

    store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")
    await store.async_remove()
