"""Test per il parsing della risposta CSV annotata di Flux (funzione pura)."""

from __future__ import annotations


from custom_components.wind_power.influx import parse_flux_csv

# Risposta tipica annotata di InfluxDB /api/v2/query.
FLUX_CSV = """#datatype,string,long,dateTime:RFC3339,double
#group,false,false,false,false
#default,_result,,,
,result,table,_time,_value
,,0,2025-01-01T00:00:00Z,5.0
,,0,2025-01-01T01:00:00Z,7.5
,,0,2025-01-01T02:00:00Z,3.2
"""


def test_parse_basic():
    samples = parse_flux_csv(FLUX_CSV)
    assert len(samples) == 3
    assert samples[0].state == "5.0"
    assert samples[0].last_changed.tzinfo is not None
    assert samples[0].last_changed.year == 2025


def test_parse_sorted():
    unsorted = """,result,table,_time,_value
,,0,2025-01-01T02:00:00Z,3.2
,,0,2025-01-01T00:00:00Z,5.0
"""
    samples = parse_flux_csv(unsorted)
    assert [s.state for s in samples] == ["5.0", "3.2"]


def test_parse_skips_empty_and_garbage():
    text = """#datatype,string,long,dateTime:RFC3339,double
,result,table,_time,_value
,,0,2025-01-01T00:00:00Z,
,,0,,4.0
,,0,not-a-date,4.0

,,0,2025-01-01T03:00:00Z,9.9
"""
    samples = parse_flux_csv(text)
    assert len(samples) == 1
    assert samples[0].state == "9.9"


def test_parse_empty_input():
    assert parse_flux_csv("") == []
