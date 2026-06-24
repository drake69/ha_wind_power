"""
Configura mock di homeassistant prima della collection dei test.

I test unitari (power.py, turbines.py) testano logica Python pura senza
il runtime di HA. Installando mock in sys.modules prima dell'import,
evitiamo la dipendenza da homeassistant nella suite di test locale.
"""
import sys
from unittest.mock import MagicMock

_HA_MOCKS = [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.event",
    "homeassistant.helpers.restore_state",
    "homeassistant.helpers.selector",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.const",
]

for _mod in _HA_MOCKS:
    sys.modules.setdefault(_mod, MagicMock())
