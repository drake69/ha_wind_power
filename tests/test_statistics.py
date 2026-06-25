"""Test per la costruzione della serie statistics (funzioni pure)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.wind_power.power import compute_power, to_ms
from custom_components.wind_power.statistics import (
    build_hourly_energy,
    statistic_id,
    to_cumulative,
)
from custom_components.wind_power.turbines import TURBINE_CATALOG

TURBINE = TURBINE_CATALOG[0]
AIR = 1.225
UNIT = "ms"
T0 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


class _S:
    def __init__(self, t: datetime, v: float) -> None:
        self.last_changed = t
        self.state = str(v)


def test_single_hour_constant_wind():
    # Due campioni a 1h di distanza, vento costante → energia = P_watt / 1000 kWh,
    # attribuita all'ora di inizio.
    wind = 8.0
    samples = [_S(T0, wind), _S(T0 + timedelta(hours=1), wind)]
    p_w = compute_power(TURBINE, to_ms(wind, UNIT), AIR)

    hourly = build_hourly_energy(samples, TURBINE, AIR, UNIT)

    assert len(hourly) == 1
    hour, kwh = hourly[0]
    assert hour == T0  # già allineata all'ora
    assert kwh == pytest.approx(p_w / 1000.0, rel=1e-9)


def test_gap_too_long_skipped():
    # Intervallo oltre MAX_GAP_SECONDS (2h) → nessuna energia attribuita.
    samples = [_S(T0, 8.0), _S(T0 + timedelta(hours=3), 8.0)]
    assert build_hourly_energy(samples, TURBINE, AIR, UNIT) == []


def test_non_numeric_state_resets():
    samples = [
        _S(T0, 8.0),
        _S(T0 + timedelta(hours=1), "unavailable"),
        _S(T0 + timedelta(hours=2), 8.0),
    ]
    # Solo il primo intervallo produce energia; il secondo parte da uno stato non valido.
    hourly = build_hourly_energy(samples, TURBINE, AIR, UNIT)
    assert all(kwh >= 0 for _, kwh in hourly)


def test_to_cumulative_running_sum():
    hourly = [(T0, 1.0), (T0 + timedelta(hours=1), 2.0), (T0 + timedelta(hours=2), 0.5)]
    cum = to_cumulative(hourly, base_sum=10.0)
    assert [v for _, v in cum] == pytest.approx([11.0, 13.0, 13.5])


def test_statistic_id_format():
    assert statistic_id("abc", "savonius") == "wind_power:abc_savonius_energy"
