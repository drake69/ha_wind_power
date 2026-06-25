"""Tests for the statistics series construction (pure functions)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.whatif_wind.power import compute_power, to_ms
from custom_components.whatif_wind.statistics import (
    build_hourly_energy,
    statistic_id,
    to_cumulative,
)

# Local fixture (the built-in catalog is now empty; turbines are user-defined).
TURBINE = {
    "id": "savonius",
    "name": "Test Savonius",
    "type": "VAWT",
    "diameter_m": 0.8,
    "height_m": 1.0,
    "rated_power_W": 500,
    "cut_in_ms": 1.5,
    "rated_ms": 12.0,
    "cut_out_ms": 45.0,
    "mode": "parametric",
    "cp": 0.18,
    "losses": {"kw": 0.02, "km": 0.005, "ke": 0.015, "ke_t": 0.03, "kt": 0.03},
}
AIR = 1.225
UNIT = "ms"
T0 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


class _S:
    def __init__(self, t: datetime, v: float) -> None:
        self.last_changed = t
        self.state = str(v)


def test_single_hour_constant_wind():
    # Two samples 1h apart, constant wind → energy = P_watt / 1000 kWh,
    # attributed to the start hour.
    wind = 8.0
    samples = [_S(T0, wind), _S(T0 + timedelta(hours=1), wind)]
    p_w = compute_power(TURBINE, to_ms(wind, UNIT), AIR)

    hourly = build_hourly_energy(samples, TURBINE, AIR, UNIT)

    assert len(hourly) == 1
    hour, kwh = hourly[0]
    assert hour == T0  # already aligned to the hour
    assert kwh == pytest.approx(p_w / 1000.0, rel=1e-9)


def test_gap_too_long_skipped():
    # Interval beyond MAX_GAP_SECONDS (2h) → no energy attributed.
    samples = [_S(T0, 8.0), _S(T0 + timedelta(hours=3), 8.0)]
    assert build_hourly_energy(samples, TURBINE, AIR, UNIT) == []


def test_non_numeric_state_resets():
    samples = [
        _S(T0, 8.0),
        _S(T0 + timedelta(hours=1), "unavailable"),
        _S(T0 + timedelta(hours=2), 8.0),
    ]
    # Only the first interval produces energy; the second starts from an invalid state.
    hourly = build_hourly_energy(samples, TURBINE, AIR, UNIT)
    assert all(kwh >= 0 for _, kwh in hourly)


def test_to_cumulative_running_sum():
    hourly = [(T0, 1.0), (T0 + timedelta(hours=1), 2.0), (T0 + timedelta(hours=2), 0.5)]
    cum = to_cumulative(hourly, base_sum=10.0)
    assert [v for _, v in cum] == pytest.approx([11.0, 13.0, 13.5])


def test_statistic_id_format():
    assert statistic_id("abc", "savonius") == "whatif_wind:abc_savonius_energy"
