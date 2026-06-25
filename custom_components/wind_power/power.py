"""Funzioni fisiche per la stima della potenza eolica."""

from __future__ import annotations

import math
from typing import Any

from .const import MAX_GAP_SECONDS, UNIT_KMH, UNIT_KN, UNIT_MPH, UNIT_MS


def to_ms(value: float, unit: str) -> float:
    """Converte la velocità del vento in m/s."""
    if unit == UNIT_KMH:
        return value / 3.6
    if unit == UNIT_MPH:
        return value * 0.44704
    if unit == UNIT_KN:
        return value * 0.514444
    return value  # già in m/s


# Mappa le stringhe `unit_of_measurement` di HA verso le nostre unità interne.
# Tollerante a varianti e maiuscole/minuscole.
_UOM_TO_UNIT = {
    "m/s": UNIT_MS,
    "ms": UNIT_MS,
    "km/h": UNIT_KMH,
    "kmh": UNIT_KMH,
    "kph": UNIT_KMH,
    "mph": UNIT_MPH,
    "mi/h": UNIT_MPH,
    "kn": UNIT_KN,
    "kt": UNIT_KN,
    "kts": UNIT_KN,
    "knot": UNIT_KN,
    "knots": UNIT_KN,
}


def detect_internal_unit(uom: str | None) -> str | None:
    """
    Deduce l'unità interna dall'attributo `unit_of_measurement` del sensore.

    Restituisce None se l'unità è assente o non riconosciuta: in quel caso
    il config flow chiede all'utente di sceglierla a mano.
    """
    if not uom:
        return None
    return _UOM_TO_UNIT.get(uom.strip().lower())


def compute_power(turbine: dict[str, Any], wind_ms: float, air_density: float) -> float:
    """Potenza stimata in watt per una data velocità del vento (m/s)."""
    if wind_ms < turbine.get("cut_in_ms", 0.0) or wind_ms > turbine.get("cut_out_ms", 999.0):
        return 0.0

    if turbine["mode"] == "tabular":
        return _power_tabular(turbine["power_curve"], wind_ms)
    return _power_parametric(turbine, wind_ms, air_density)


def _power_parametric(turbine: dict[str, Any], wind_ms: float, air_density: float) -> float:
    if turbine["type"] == "HAWT":
        area = math.pi * turbine["blade_length_m"] ** 2
    else:  # VAWT
        area = turbine["diameter_m"] * turbine["height_m"]

    p_wind = 0.5 * air_density * wind_ms**3 * area
    losses = turbine.get("losses", {})
    mu = (
        turbine["cp"]
        * (1 - losses.get("kw", 0.0))
        * (1 - losses.get("km", 0.0))
        * (1 - losses.get("ke", 0.0))
        * (1 - losses.get("ke_t", 0.0))
        * (1 - losses.get("kt", 0.0))
    )
    return mu * p_wind


def _power_tabular(curve: list[list[float]], wind_ms: float) -> float:
    """Interpolazione lineare sulla curva di potenza del produttore."""
    for i in range(len(curve) - 1):
        v0, p0 = curve[i]
        v1, p1 = curve[i + 1]
        if v0 <= wind_ms <= v1:
            if v1 == v0:
                return float(p0)
            return p0 + (p1 - p0) * (wind_ms - v0) / (v1 - v0)
    return float(curve[-1][1])


def compute_simulated_energy_kwh(
    states: list,
    turbine: dict[str, Any],
    air_density: float,
    wind_unit: str,
) -> float:
    """
    Energia totale simulata in kWh su una lista di stati HA.

    Usa la regola dei trapezi: per ogni intervallo tra due campioni consecutivi
    si media la potenza agli estremi e la si moltiplica per la durata.
    Intervalli > MAX_GAP_SECONDS vengono saltati perché il sensore era
    probabilmente offline e il vento reale è ignoto.
    """
    total_kwh = 0.0
    prev_time = None
    prev_power_w = 0.0

    for state in states:
        try:
            raw = float(state.state)
        except (ValueError, TypeError):
            prev_time = getattr(state, "last_changed", None)
            prev_power_w = 0.0
            continue

        wind_ms = to_ms(raw, wind_unit)
        power_w = compute_power(turbine, wind_ms, air_density)

        if prev_time is not None:
            dt_s = (state.last_changed - prev_time).total_seconds()
            if 0 < dt_s <= MAX_GAP_SECONDS:
                avg_w = (prev_power_w + power_w) / 2.0
                total_kwh += avg_w * dt_s / 3_600_000.0

        prev_time = state.last_changed
        prev_power_w = power_w

    return total_kwh
