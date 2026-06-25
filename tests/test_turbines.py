"""Tests for the turbine helpers in turbines.py."""

from __future__ import annotations

import pytest

from custom_components.whatif_wind.const import (
    CONF_T_BLADE_LENGTH,
    CONF_T_CP,
    CONF_T_CUT_IN,
    CONF_T_CUT_OUT,
    CONF_T_DIAMETER,
    CONF_T_HEIGHT,
    CONF_T_NAME,
    CONF_T_POWER_CURVE,
    CONF_T_RATED_POWER,
    CONF_T_SUBTYPE,
    CP_DEFAULTS,
    SUBTYPE_HAWT_3BLADE,
    SUBTYPE_VAWT_SAVONIUS,
)
from custom_components.whatif_wind.turbines import (
    TURBINE_CATALOG,
    build_turbine,
    parse_power_curve,
    resolve_turbines,
    slugify,
    unique_id,
)

# ─── catalog / resolve ────────────────────────────────────────────────────────


def test_builtin_catalog_is_empty():
    assert TURBINE_CATALOG == []


def test_resolve_turbines_merges_custom():
    custom = [{"id": "a"}, {"id": "b"}]
    assert resolve_turbines(custom) == custom


def test_resolve_turbines_handles_none():
    assert resolve_turbines(None) == []


# ─── slugify / unique_id ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Bornay Wind 13+", "bornay_wind_13"),
        ("  SD6  ", "sd6"),
        ("Éolienne ###", "olienne"),
        ("", "turbine"),
        ("---", "turbine"),
    ],
)
def test_slugify(name, expected):
    assert slugify(name) == expected


def test_unique_id_no_collision():
    assert unique_id("Turbine X", set()) == "turbine_x"


def test_unique_id_disambiguates():
    existing = {"turbine_x", "turbine_x_2"}
    assert unique_id("Turbine X", existing) == "turbine_x_3"


# ─── parse_power_curve ────────────────────────────────────────────────────────


def test_parse_power_curve_comma_and_sorted():
    curve = parse_power_curve("10,1000\n0,0\n5,400")
    assert curve == [[0.0, 0.0], [5.0, 400.0], [10.0, 1000.0]]


def test_parse_power_curve_whitespace_and_blank_lines():
    curve = parse_power_curve("0 0\n\n  3   50  \n")
    assert curve == [[0.0, 0.0], [3.0, 50.0]]


@pytest.mark.parametrize("text", ["", "10,1000", "0,0\nabc,5", "0\n1,2"])
def test_parse_power_curve_invalid(text):
    with pytest.raises(ValueError):
        parse_power_curve(text)


# ─── build_turbine ────────────────────────────────────────────────────────────


def _hawt_input(**over):
    data = {
        CONF_T_NAME: "My HAWT",
        CONF_T_SUBTYPE: SUBTYPE_HAWT_3BLADE,
        CONF_T_BLADE_LENGTH: 1.5,
        CONF_T_RATED_POWER: 3000,
    }
    data.update(over)
    return data


def _vawt_input(**over):
    data = {
        CONF_T_NAME: "My VAWT",
        CONF_T_SUBTYPE: SUBTYPE_VAWT_SAVONIUS,
        CONF_T_DIAMETER: 0.8,
        CONF_T_HEIGHT: 1.2,
        CONF_T_RATED_POWER: 500,
    }
    data.update(over)
    return data


def test_build_hawt_parametric_defaults_cp():
    t = build_turbine(_hawt_input())
    assert t["type"] == "HAWT"
    assert t["mode"] == "parametric"
    assert t["blade_length_m"] == 1.5
    assert t["rated_power_W"] == 3000
    assert t["cp"] == CP_DEFAULTS[SUBTYPE_HAWT_3BLADE]
    assert t["id"] == "my_hawt"
    assert "losses" in t


def test_build_vawt_parametric_geometry():
    t = build_turbine(_vawt_input())
    assert t["type"] == "VAWT"
    assert t["diameter_m"] == 0.8
    assert t["height_m"] == 1.2
    assert t["cp"] == CP_DEFAULTS[SUBTYPE_VAWT_SAVONIUS]


def test_build_cp_override():
    t = build_turbine(_hawt_input(**{CONF_T_CP: 0.25}))
    assert t["cp"] == 0.25


def test_build_tabular_when_curve_given():
    t = build_turbine(_hawt_input(**{CONF_T_POWER_CURVE: "0,0\n10,3000"}))
    assert t["mode"] == "tabular"
    assert t["power_curve"] == [[0.0, 0.0], [10.0, 3000.0]]
    assert "cp" not in t


def test_build_unique_id_against_existing():
    t = build_turbine(_hawt_input(), existing_ids={"my_hawt"})
    assert t["id"] == "my_hawt_2"


@pytest.mark.parametrize(
    "over",
    [
        {CONF_T_NAME: "   "},
        {CONF_T_SUBTYPE: "bogus"},
        {CONF_T_RATED_POWER: 0},
        {CONF_T_BLADE_LENGTH: 0},
        {CONF_T_CP: 0.7},  # above Betz
        {CONF_T_CUT_IN: 10, CONF_T_CUT_OUT: 5},
    ],
)
def test_build_turbine_invalid(over):
    with pytest.raises(ValueError):
        build_turbine(_hawt_input(**over))
