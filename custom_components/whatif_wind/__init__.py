"""WhatIfWind — HACS integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import WhatIfWindCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = WhatIfWindCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload when the user adds/removes a turbine from the options flow.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean uninstall: remove external statistics and the persisted state.

    Statistics and the Store survive an unload (they live in the recorder and in
    .storage): without this cleanup they would be orphaned after removal.
    """
    from homeassistant.helpers.storage import Store

    from .const import CONF_CUSTOM_TURBINES
    from .statistics import async_clear_statistics, statistic_id
    from .turbines import resolve_turbines

    turbines = resolve_turbines(entry.options.get(CONF_CUSTOM_TURBINES, []))
    stat_ids = [statistic_id(entry.entry_id, t["id"]) for t in turbines]
    await async_clear_statistics(hass, stat_ids)

    store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")
    await store.async_remove()
