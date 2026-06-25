"""
Turbine catalog and helpers for user-defined turbines.

Turbines are no longer hardcoded: the user adds them from Home Assistant
(Settings → Devices & Services → WhatIfWind → Configure). Each turbine is stored
in the config entry options and merged with the (currently empty) built-in
catalog at runtime.

mode "parametric": physics-based (swept area × Cp × air density × v³), capped at
  the nameplate power. The user only provides the geometry; Cp comes from the
  subtype default and can be overridden.

mode "tabular": uses the [speed_ms, power_W] table from the datasheet. More
  accurate; interpolation is linear between points.

Supported types:
  HAWT — horizontal axis. Area = π × blade_length_m²
  VAWT — vertical axis (Savonius, Darrieus, H-rotor). Area = diameter_m × height_m
"""

from __future__ import annotations

import re
from typing import Any

from .const import (
    BETZ_LIMIT,
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
    DEFAULT_CUT_IN_MS,
    DEFAULT_CUT_OUT_MS,
    DEFAULT_LOSSES,
    SUBTYPE_TO_TYPE,
)

# No built-in turbines: the user defines their own from the UI.
TURBINE_CATALOG: list[dict] = []


def resolve_turbines(custom_turbines: list[dict] | None) -> list[dict]:
    """Return the turbines available for a config entry: built-in + user-defined."""
    return [*TURBINE_CATALOG, *(custom_turbines or [])]


def slugify(name: str) -> str:
    """Build a stable, filesystem/statistic-safe id from a turbine name."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "turbine"


def unique_id(name: str, existing_ids: set[str] | None = None) -> str:
    """Slugify `name` and disambiguate against `existing_ids` with a numeric suffix."""
    existing = existing_ids or set()
    base = slugify(name)
    if base not in existing:
        return base
    i = 2
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"


def parse_power_curve(text: str) -> list[list[float]]:
    """Parse a multiline ``speed,power`` text into a sorted ``[[v, w], ...]`` curve.

    Accepts comma- or whitespace-separated pairs, one per line; blank lines are
    ignored. Raises ValueError on malformed input or fewer than two points.
    """
    curve: list[list[float]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = re.split(r"[\s,;]+", line)
        if len(parts) != 2:
            raise ValueError(f"Line {lineno}: expected 'speed,power', got {raw!r}")
        try:
            v, w = float(parts[0]), float(parts[1])
        except ValueError as err:
            raise ValueError(f"Line {lineno}: not a number — {raw!r}") from err
        curve.append([v, w])
    if len(curve) < 2:
        raise ValueError("The power curve needs at least two points")
    curve.sort(key=lambda pt: pt[0])
    return curve


def build_turbine(data: dict[str, Any], existing_ids: set[str] | None = None) -> dict:
    """Build a validated turbine dict from options-flow input.

    `data` carries the form fields (name, subtype, geometry, rated_power_W and
    the optional advanced cp/cut-in/cut-out/power_curve). Raises ValueError on
    invalid input.
    """
    name = str(data.get(CONF_T_NAME, "")).strip()
    if not name:
        raise ValueError("Name is required")

    subtype = data.get(CONF_T_SUBTYPE)
    if subtype not in SUBTYPE_TO_TYPE:
        raise ValueError(f"Unknown subtype: {subtype!r}")
    turbine_type = SUBTYPE_TO_TYPE[subtype]

    rated_power_w = float(data.get(CONF_T_RATED_POWER, 0) or 0)
    if rated_power_w <= 0:
        raise ValueError("Rated power must be greater than 0")

    cut_in = float(data.get(CONF_T_CUT_IN, DEFAULT_CUT_IN_MS))
    cut_out = float(data.get(CONF_T_CUT_OUT, DEFAULT_CUT_OUT_MS))
    if not 0 <= cut_in < cut_out:
        raise ValueError("Cut-in must be ≥ 0 and lower than cut-out")

    turbine: dict[str, Any] = {
        "id": unique_id(name, existing_ids),
        "name": name,
        "manufacturer": "—",
        "model": name,
        "subtype": subtype,
        "type": turbine_type,
        "rated_power_W": rated_power_w,
        "cut_in_ms": cut_in,
        "cut_out_ms": cut_out,
    }

    # Geometry (the swept area depends on the rotor axis).
    if turbine_type == "HAWT":
        blade = float(data.get(CONF_T_BLADE_LENGTH, 0) or 0)
        if blade <= 0:
            raise ValueError("Blade length must be greater than 0")
        turbine[CONF_T_BLADE_LENGTH] = blade
    else:
        diameter = float(data.get(CONF_T_DIAMETER, 0) or 0)
        height = float(data.get(CONF_T_HEIGHT, 0) or 0)
        if diameter <= 0 or height <= 0:
            raise ValueError("Diameter and height must be greater than 0")
        turbine[CONF_T_DIAMETER] = diameter
        turbine[CONF_T_HEIGHT] = height

    # A non-empty power curve switches the turbine to tabular mode.
    curve_text = str(data.get(CONF_T_POWER_CURVE, "") or "").strip()
    if curve_text:
        turbine["mode"] = "tabular"
        turbine["power_curve"] = parse_power_curve(curve_text)
    else:
        cp = float(data.get(CONF_T_CP) or CP_DEFAULTS[subtype])
        if not 0 < cp <= BETZ_LIMIT:
            raise ValueError(f"Cp must be in (0, {BETZ_LIMIT}]")
        turbine["mode"] = "parametric"
        turbine["cp"] = cp
        turbine["losses"] = dict(DEFAULT_LOSSES)

    return turbine
