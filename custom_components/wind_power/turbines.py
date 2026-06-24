"""
Turbine catalog.

Aggiungi qui i modelli reali che stai valutando.

mode "parametric": usa Cp + perdite. Adatto quando non si dispone della curva
  del produttore. Le differenze di efficienza tra sottotipi (es. Savonius vs
  H-rotor per i VAWT) si catturano modificando cp.

mode "tabular": usa la tabella [velocità_ms, potenza_W] della scheda tecnica.
  Più accurato; l'interpolazione è lineare tra i punti.

Tipi supportati:
  HAWT — asse orizzontale. Area = π × blade_length_m²
  VAWT — asse verticale (Savonius, Darrieus, H-rotor, elicoidale).
          Area = diameter_m × height_m
"""
from __future__ import annotations

TURBINE_CATALOG: list[dict] = [
    {
        "id": "vawt_savonius_500w",
        "name": "VAWT Savonius 500 W",
        "manufacturer": "Esempio",
        "model": "Savonius 500",
        "type": "VAWT",
        "diameter_m": 0.8,
        "height_m": 1.0,
        "rated_power_W": 500,
        "cut_in_ms": 1.5,
        "rated_ms": 12.0,
        "cut_out_ms": 45.0,
        "mode": "parametric",
        # Savonius: drag-based, Cp basso ma cut-in molto basso
        "cp": 0.18,
        "losses": {
            "kw": 0.02,   # perdite scia
            "km": 0.005,  # meccaniche
            "ke": 0.015,  # elettriche
            "ke_t": 0.03, # trasmissione
            "kt": 0.03,   # downtime
        },
    },
    {
        "id": "hawt_tripala_1kw",
        "name": "HAWT Tripala 1 kW",
        "manufacturer": "Esempio",
        "model": "Tripala 1000",
        "type": "HAWT",
        "blade_length_m": 1.25,
        "rated_power_W": 1000,
        "cut_in_ms": 2.5,
        "rated_ms": 11.0,
        "cut_out_ms": 60.0,
        "mode": "tabular",
        # Curva di esempio: [velocità m/s, potenza W]
        # Sostituire con i dati reali della scheda tecnica del produttore
        "power_curve": [
            [0.0,   0],
            [1.0,   0],
            [2.0,   0],
            [2.5,  20],
            [3.0,  50],
            [4.0, 120],
            [5.0, 220],
            [6.0, 370],
            [7.0, 530],
            [8.0, 700],
            [9.0, 850],
            [10.0, 950],
            [11.0, 1000],
            [15.0, 1000],
            [25.0, 1000],
            [60.0, 1000],
        ],
    },
    {
        "id": "vawt_hrotor_2kw",
        "name": "VAWT H-rotor 2 kW",
        "manufacturer": "Esempio",
        "model": "Giromill 2000",
        "type": "VAWT",
        "diameter_m": 1.5,
        "height_m": 2.0,
        "rated_power_W": 2000,
        "cut_in_ms": 3.0,
        "rated_ms": 12.0,
        "cut_out_ms": 45.0,
        "mode": "parametric",
        # H-rotor/Darrieus: lift-based, Cp più alto del Savonius
        "cp": 0.32,
        "losses": {
            "kw": 0.03,
            "km": 0.005,
            "ke": 0.015,
            "ke_t": 0.05,
            "kt": 0.03,
        },
    },
]
