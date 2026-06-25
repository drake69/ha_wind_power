"""Validazione del catalogo turbine in turbines.py."""

from __future__ import annotations

import pytest

from custom_components.wind_power.turbines import TURBINE_CATALOG


def test_catalog_non_vuoto():
    assert len(TURBINE_CATALOG) > 0


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_campi_obbligatori(turbine):
    required = {
        "id",
        "name",
        "type",
        "mode",
        "rated_power_W",
        "cut_in_ms",
        "rated_ms",
        "cut_out_ms",
    }
    missing = required - turbine.keys()
    assert not missing, f"Campi mancanti: {missing}"


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_tipo_valido(turbine):
    assert turbine["type"] in ("HAWT", "VAWT")


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_modo_valido(turbine):
    assert turbine["mode"] in ("parametric", "tabular")


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_velocità_ordinate(turbine):
    assert turbine["cut_in_ms"] < turbine["rated_ms"] < turbine["cut_out_ms"], (
        "Deve valere: cut_in < rated < cut_out"
    )


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_potenza_nominale_positiva(turbine):
    assert turbine["rated_power_W"] > 0


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_geometria_hawt_parametrica(turbine):
    if turbine["type"] == "HAWT" and turbine["mode"] == "parametric":
        assert "blade_length_m" in turbine
        assert turbine["blade_length_m"] > 0


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_geometria_vawt_parametrica(turbine):
    if turbine["type"] == "VAWT" and turbine["mode"] == "parametric":
        assert "diameter_m" in turbine and "height_m" in turbine
        assert turbine["diameter_m"] > 0 and turbine["height_m"] > 0


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_cp_nel_range_betz(turbine):
    if turbine["mode"] == "parametric":
        assert 0 < turbine["cp"] <= 0.593, f"Cp={turbine['cp']} fuori dal range fisico (0, 0.593]"


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_perdite_nel_range(turbine):
    if turbine["mode"] == "parametric":
        for key, val in turbine.get("losses", {}).items():
            assert 0.0 <= val < 1.0, f"Perdita {key}={val} fuori range [0, 1)"


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_curva_tabulare_valida(turbine):
    if turbine["mode"] != "tabular":
        return
    curve = turbine["power_curve"]
    assert len(curve) >= 2, "La curva deve avere almeno 2 punti"
    speeds = [pt[0] for pt in curve]
    powers = [pt[1] for pt in curve]
    assert speeds == sorted(speeds), "I punti della curva devono essere ordinati per velocità"
    assert all(p >= 0 for p in powers), "La potenza non può essere negativa"


@pytest.mark.parametrize("turbine", TURBINE_CATALOG, ids=lambda t: t["id"])
def test_id_univoci(turbine):
    ids = [t["id"] for t in TURBINE_CATALOG]
    assert ids.count(turbine["id"]) == 1, f"ID duplicato: {turbine['id']}"
