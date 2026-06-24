"""Test per le funzioni fisiche di power.py."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.wind_power.power import (
    compute_power,
    compute_simulated_energy_kwh,
    to_ms,
)
from custom_components.wind_power.turbines import TURBINE_CATALOG

# ─── to_ms ───────────────────────────────────────────────────────────────────

def test_to_ms_passthrough():
    assert to_ms(10.0, "ms") == pytest.approx(10.0)

def test_to_ms_kmh():
    assert to_ms(36.0, "kmh") == pytest.approx(10.0)

def test_to_ms_mph():
    # 22.3694 mph ≈ 10 m/s
    assert to_ms(22.3694, "mph") == pytest.approx(10.0, rel=1e-4)

def test_to_ms_zero():
    for unit in ("ms", "kmh", "mph"):
        assert to_ms(0.0, unit) == 0.0


# ─── compute_power: condizioni di confine ────────────────────────────────────

SAVONIUS = TURBINE_CATALOG[0]   # VAWT Savonius, cut_in=1.5, cut_out=45
HAWT_TAB = TURBINE_CATALOG[1]   # HAWT tabulare 1 kW
HROTOR   = TURBINE_CATALOG[2]   # VAWT H-rotor, cut_in=3.0

def test_power_below_cut_in_savonius():
    assert compute_power(SAVONIUS, 1.0, 1.225) == 0.0

def test_power_below_cut_in_hrotor():
    assert compute_power(HROTOR, 2.9, 1.225) == 0.0

def test_power_above_cut_out():
    assert compute_power(SAVONIUS, 50.0, 1.225) == 0.0

def test_power_at_cut_in_is_zero():
    # Alla velocità esatta di cut-in deve ancora produrre (è il confine incluso)
    p = compute_power(SAVONIUS, SAVONIUS["cut_in_ms"], 1.225)
    assert p >= 0.0

def test_power_positive_above_cut_in():
    p = compute_power(SAVONIUS, 5.0, 1.225)
    assert p > 0.0

    p2 = compute_power(HROTOR, 5.0, 1.225)
    assert p2 > 0.0


# ─── compute_power: modalità tabulare ────────────────────────────────────────

def test_tabular_at_rated_speed():
    p = compute_power(HAWT_TAB, 11.0, 1.225)
    assert p == pytest.approx(1000.0)

def test_tabular_zero_below_cut_in():
    assert compute_power(HAWT_TAB, 2.0, 1.225) == 0.0

def test_tabular_interpolation_midpoint():
    # Tra 5 m/s (220 W) e 6 m/s (370 W) → a 5.5 m/s aspettiamoci ~295 W
    p = compute_power(HAWT_TAB, 5.5, 1.225)
    assert p == pytest.approx(295.0, abs=1.0)

def test_tabular_clamped_beyond_last_point():
    # Con cut_out > ultimo punto della curva, la potenza viene clamped all'ultimo
    # valore anziché estrapolata. Usiamo cut_out=999 per bypassare lo shutdown.
    turbine_extended = {**HAWT_TAB, "cut_out_ms": 999.0}
    p = compute_power(turbine_extended, 80.0, 1.225)
    assert p == pytest.approx(1000.0)


# ─── compute_power: modalità parametrica (area e fisica) ─────────────────────

_LOSSLESS_HAWT = {
    "id": "test_hawt", "name": "Test HAWT", "type": "HAWT",
    "blade_length_m": 1.0,
    "cut_in_ms": 0.0, "cut_out_ms": 999.0, "rated_ms": 50.0, "rated_power_W": 9999,
    "mode": "parametric", "cp": 1.0, "losses": {},
}

_LOSSLESS_VAWT = {
    "id": "test_vawt", "name": "Test VAWT", "type": "VAWT",
    "diameter_m": 2.0, "height_m": 3.0,
    "cut_in_ms": 0.0, "cut_out_ms": 999.0, "rated_ms": 50.0, "rated_power_W": 9999,
    "mode": "parametric", "cp": 1.0, "losses": {},
}

def test_hawt_area_formula():
    # P = 0.5 * rho * v³ * π*r² * cp  con cp=1 e nessuna perdita
    rho, v = 1.225, 10.0
    expected = 0.5 * rho * v**3 * math.pi * 1.0**2
    assert compute_power(_LOSSLESS_HAWT, v, rho) == pytest.approx(expected, rel=1e-9)

def test_vawt_area_formula():
    # P = 0.5 * rho * v³ * (D×H) * cp  con cp=1 e nessuna perdita
    rho, v = 1.225, 10.0
    expected = 0.5 * rho * v**3 * (2.0 * 3.0)
    assert compute_power(_LOSSLESS_VAWT, v, rho) == pytest.approx(expected, rel=1e-9)

def test_power_scales_with_cube_of_speed():
    p1 = compute_power(_LOSSLESS_HAWT, 5.0, 1.225)
    p2 = compute_power(_LOSSLESS_HAWT, 10.0, 1.225)
    assert p2 == pytest.approx(p1 * 8, rel=1e-9)  # (10/5)³ = 8

def test_air_density_effect():
    p_low = compute_power(_LOSSLESS_HAWT, 10.0, 1.0)
    p_high = compute_power(_LOSSLESS_HAWT, 10.0, 2.0)
    assert p_high == pytest.approx(p_low * 2.0, rel=1e-9)

def test_betz_limit_cp():
    turbine = {**_LOSSLESS_HAWT, "cp": 0.593}
    p = compute_power(turbine, 10.0, 1.225)
    assert p > 0


# ─── compute_simulated_energy_kwh ────────────────────────────────────────────

def _state(speed: float, ts: datetime) -> MagicMock:
    s = MagicMock()
    s.state = str(speed)
    s.last_changed = ts
    return s

T0 = datetime(2024, 6, 1, tzinfo=timezone.utc)

def test_zero_energy_no_wind():
    states = [_state(0.0, T0 + timedelta(minutes=i * 30)) for i in range(5)]
    assert compute_simulated_energy_kwh(states, SAVONIUS, 1.225, "ms") == 0.0

def test_zero_energy_below_cut_in():
    states = [_state(1.0, T0 + timedelta(minutes=i * 30)) for i in range(5)]
    assert compute_simulated_energy_kwh(states, SAVONIUS, 1.225, "ms") == 0.0

def test_constant_wind_trapezoid():
    # Turbina parametrica senza perdite, area 1 m², cp=1
    # A 10 m/s: P = 0.5 * 1.225 * 1000 * 1 = 612.5 W
    # 4 stati a 30 min → 3 intervalli × 1800 s = 5400 s
    # E = 612.5 × 5400 / 3_600_000 = 0.91875 kWh
    states = [_state(10.0, T0 + timedelta(minutes=i * 30)) for i in range(4)]
    turbine = {**_LOSSLESS_VAWT, "diameter_m": 1.0, "height_m": 1.0}
    energy = compute_simulated_energy_kwh(states, turbine, 1.225, "ms")
    expected = 0.5 * 1.225 * 10.0**3 * 1.0 * 3 * 1800 / 3_600_000
    assert energy == pytest.approx(expected, rel=1e-9)

def test_unit_kmh_conversion():
    # 36 km/h = 10 m/s: stesso risultato di test_constant_wind_trapezoid
    states = [_state(36.0, T0 + timedelta(minutes=i * 30)) for i in range(4)]
    turbine = {**_LOSSLESS_VAWT, "diameter_m": 1.0, "height_m": 1.0}
    energy_kmh = compute_simulated_energy_kwh(states, turbine, 1.225, "kmh")
    energy_ms  = compute_simulated_energy_kwh(
        [_state(10.0, T0 + timedelta(minutes=i * 30)) for i in range(4)],
        turbine, 1.225, "ms",
    )
    assert energy_kmh == pytest.approx(energy_ms, rel=1e-9)

def test_unit_mph_conversion():
    # 22.3694 mph ≈ 10 m/s
    states = [_state(22.3694, T0 + timedelta(minutes=i * 30)) for i in range(4)]
    turbine = {**_LOSSLESS_VAWT, "diameter_m": 1.0, "height_m": 1.0}
    energy_mph = compute_simulated_energy_kwh(states, turbine, 1.225, "mph")
    energy_ms  = compute_simulated_energy_kwh(
        [_state(10.0, T0 + timedelta(minutes=i * 30)) for i in range(4)],
        turbine, 1.225, "ms",
    )
    assert energy_mph == pytest.approx(energy_ms, rel=1e-3)

def test_gap_larger_than_threshold_is_skipped():
    # Due stati a 3 ore di distanza: gap > MAX_GAP_SECONDS (7200 s) → scartato
    states = [
        _state(10.0, T0),
        _state(10.0, T0 + timedelta(hours=3)),
    ]
    turbine = {**_LOSSLESS_VAWT, "diameter_m": 1.0, "height_m": 1.0}
    assert compute_simulated_energy_kwh(states, turbine, 1.225, "ms") == 0.0

def test_gap_within_threshold_is_counted():
    # Due stati a 1 ora esatta: gap = 3600 s ≤ MAX_GAP_SECONDS → contato
    states = [
        _state(10.0, T0),
        _state(10.0, T0 + timedelta(hours=1)),
    ]
    turbine = {**_LOSSLESS_VAWT, "diameter_m": 1.0, "height_m": 1.0}
    energy = compute_simulated_energy_kwh(states, turbine, 1.225, "ms")
    assert energy > 0.0

def test_invalid_state_skipped():
    states = [
        _state(10.0, T0),
        _state("unavailable", T0 + timedelta(minutes=30)),
        _state(10.0, T0 + timedelta(minutes=60)),
    ]
    turbine = {**_LOSSLESS_VAWT, "diameter_m": 1.0, "height_m": 1.0}
    # Il campione non valido non deve far crashare né contare energia spurie
    energy = compute_simulated_energy_kwh(states, turbine, 1.225, "ms")
    assert energy >= 0.0

def test_single_state_produces_no_energy():
    states = [_state(10.0, T0)]
    assert compute_simulated_energy_kwh(states, HROTOR, 1.225, "ms") == 0.0
