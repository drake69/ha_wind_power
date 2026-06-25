"""Costruzione e scrittura della serie storica come long-term statistics ESTERNE.

La serie giorno/mese/anno NON è energia reale: è una stima di produzione
potenziale. Per questo vive come statistics esterne (`wind_power:...`) e non
come entità `device_class=energy` — così non finisce nella dashboard energia
di HA come fosse un contatore vero.

Le statistics esterne con `has_sum` reggono sia il backfill retrodatato
(`async_add_external_statistics` accetta start nel passato) sia l'append in
avanti: stessa `statistic_id`, somma cumulativa che continua a crescere.
"""

from __future__ import annotations

from datetime import datetime

from .const import DOMAIN, MAX_GAP_SECONDS
from .power import compute_power, to_ms


def statistic_id(entry_id: str, turbine_id: str) -> str:
    """ID statistic esterna per la serie energia di una turbina."""
    return f"{DOMAIN}:{entry_id}_{turbine_id}_energy"


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def build_hourly_energy(
    samples: list,
    turbine: dict,
    air_density: float,
    wind_unit: str,
) -> list[tuple[datetime, float]]:
    """
    Energia stimata (kWh) per ogni ora coperta dai campioni.

    Calcola l'incremento di energia tra campioni consecutivi (regola dei
    trapezi) e lo attribuisce all'ora di inizio dell'intervallo. Intervalli
    più lunghi di MAX_GAP_SECONDS vengono saltati (sensore probabilmente
    offline). Restituisce coppie (ora_UTC, kWh) ordinate, una per ora non vuota.
    """
    buckets: dict[datetime, float] = {}
    prev_time = None
    prev_power_w = 0.0

    for sample in samples:
        try:
            raw = float(sample.state)
        except (ValueError, TypeError):
            prev_time = getattr(sample, "last_changed", None)
            prev_power_w = 0.0
            continue

        power_w = compute_power(turbine, to_ms(raw, wind_unit), air_density)

        if prev_time is not None:
            dt_s = (sample.last_changed - prev_time).total_seconds()
            if 0 < dt_s <= MAX_GAP_SECONDS:
                avg_w = (prev_power_w + power_w) / 2.0
                kwh = avg_w * dt_s / 3_600_000.0
                hour = _floor_hour(prev_time)
                buckets[hour] = buckets.get(hour, 0.0) + kwh

        prev_time = sample.last_changed
        prev_power_w = power_w

    return sorted(buckets.items())


def to_cumulative(
    hourly: list[tuple[datetime, float]], base_sum: float = 0.0
) -> list[tuple[datetime, float]]:
    """Trasforma (ora, kWh) in (ora, somma_cumulativa) partendo da base_sum."""
    running = base_sum
    out: list[tuple[datetime, float]] = []
    for hour, kwh in hourly:
        running += kwh
        out.append((hour, running))
    return out


async def async_write_statistics(
    hass,
    stat_id: str,
    name: str,
    cumulative: list[tuple[datetime, float]],
) -> None:
    """Scrive/aggiorna la serie statistics esterna (somma cumulativa per ora)."""
    if not cumulative:
        return
    from homeassistant.components.recorder.models import (
        StatisticData,
        StatisticMetaData,
    )
    from homeassistant.components.recorder.statistics import (
        async_add_external_statistics,
    )

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=name,
        source=DOMAIN,
        statistic_id=stat_id,
        unit_of_measurement="kWh",
    )
    stats = [StatisticData(start=hour, state=value, sum=value) for hour, value in cumulative]
    async_add_external_statistics(hass, metadata, stats)


async def async_clear_statistics(hass, stat_ids: list[str]) -> None:
    """Rimuove le statistics esterne (disinstallazione pulita)."""
    if not stat_ids:
        return
    from homeassistant.components.recorder import get_instance

    get_instance(hass).async_clear_statistics(stat_ids)
