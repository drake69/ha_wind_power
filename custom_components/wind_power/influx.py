"""Client InfluxDB minimale — sola lettura via HTTP API nativa (Flux).

Nessuna libreria nel manifest: una singola POST autenticata a /api/v2/query,
risposta CSV annotata che parsiamo a mano. Importato in modo lazy: se la
sorgente backfill non è InfluxDB, questo modulo non viene mai caricato.

I campioni restituiti sono già aggregati a media oraria lato InfluxDB. È un
compromesso voluto: la potenza va come v³ (convessa), quindi l'oraria è la
risoluzione più fine che ha senso pre-mediare senza sottostimare in modo
sensibile, e tiene leggero un anno di dati.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Sample:
    """Campione compatibile con compute_simulated_energy_kwh (.state, .last_changed)."""

    last_changed: datetime
    state: str


class InfluxError(Exception):
    """Errore di lettura da InfluxDB (rete, auth, query, parsing)."""


def _build_flux(bucket: str, measurement: str, field: str, days: int) -> str:
    return (
        f'from(bucket: "{bucket}")\n'
        f"  |> range(start: -{days}d)\n"
        f'  |> filter(fn: (r) => r._measurement == "{measurement}" '
        f'and r._field == "{field}")\n'
        f"  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)\n"
        f'  |> keep(columns: ["_time", "_value"])\n'
    )


def parse_flux_csv(text: str) -> list[Sample]:
    """
    Parsa la risposta CSV annotata di Flux in una lista di Sample ordinati.

    Tollera le righe di annotazione (#...), le righe vuote tra tabelle e
    l'ordine variabile delle colonne (usa l'header per trovare _time/_value).
    """
    samples: list[Sample] = []
    time_idx: int | None = None
    value_idx: int | None = None

    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split(",")
        if "_time" in cols and "_value" in cols:
            # riga di header: fissa gli indici di colonna per la tabella corrente
            time_idx = cols.index("_time")
            value_idx = cols.index("_value")
            continue
        if time_idx is None or value_idx is None:
            continue
        if max(time_idx, value_idx) >= len(cols):
            continue
        raw_time = cols[time_idx].strip()
        raw_value = cols[value_idx].strip()
        if not raw_time or not raw_value:
            continue
        try:
            ts = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            continue
        samples.append(Sample(last_changed=ts, state=raw_value))

    samples.sort(key=lambda s: s.last_changed)
    return samples


async def async_fetch_wind_samples(hass, cfg: dict, days: int) -> list[Sample]:
    """Scarica i campioni orari di vento dall'ultimo `days`-esimo giorno a oggi."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .const import (
        CONF_INFLUX_BUCKET,
        CONF_INFLUX_FIELD,
        CONF_INFLUX_MEASUREMENT,
        CONF_INFLUX_ORG,
        CONF_INFLUX_TOKEN,
        CONF_INFLUX_URL,
    )

    url = cfg[CONF_INFLUX_URL].rstrip("/") + "/api/v2/query"
    flux = _build_flux(
        cfg[CONF_INFLUX_BUCKET],
        cfg[CONF_INFLUX_MEASUREMENT],
        cfg[CONF_INFLUX_FIELD],
        days,
    )
    headers = {
        "Authorization": f"Token {cfg[CONF_INFLUX_TOKEN]}",
        "Content-Type": "application/vnd.flux",
        "Accept": "application/csv",
    }
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            url,
            params={"org": cfg[CONF_INFLUX_ORG]},
            data=flux,
            headers=headers,
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise InfluxError(f"HTTP {resp.status}: {body[:200]}")
            text = await resp.text()
    except InfluxError:
        raise
    except Exception as err:  # noqa: BLE001 — rete/timeout/DNS: li normalizziamo
        raise InfluxError(str(err)) from err

    return parse_flux_csv(text)
