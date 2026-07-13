from pathlib import Path

import pytest

from reviewerfinder.models import Zone
from reviewerfinder.rules import zones as zones_mod

ZONES_FILE = Path(__file__).resolve().parents[2] / "data" / "seed" / "zones.yaml"


@pytest.fixture(autouse=True)
def clear_cache():
    zones_mod._load_zone_map.cache_clear()
    yield
    zones_mod._load_zone_map.cache_clear()


@pytest.mark.parametrize(
    "country_code,expected",
    [
        ("US", Zone.ZONE_1),
        ("GB", Zone.ZONE_1),
        ("FR", Zone.ZONE_1),
        ("DE", Zone.ZONE_1),
        ("JP", Zone.ZONE_1),
        ("PL", Zone.ZONE_1),
        ("RU", Zone.ZONE_1),
        ("HU", Zone.ZONE_1),
        ("CN", Zone.ZONE_2),
        ("AE", Zone.ZONE_2),
        ("BR", Zone.ZONE_2),
        ("MA", Zone.ZONE_2),
        ("CO", Zone.ZONE_2),
        ("CL", Zone.ZONE_2),
        ("IN", Zone.ZONE_3),
        ("TH", Zone.ZONE_3),
        ("MY", Zone.ZONE_3),
        ("IQ", Zone.ZONE_3),
        ("IR", Zone.ZONE_3),
        ("TR", Zone.ZONE_3),
        ("VN", Zone.ZONE_3),  # not explicitly listed -> catch-all "and the rest"
        ("ZZ", Zone.ZONE_3),  # unmapped -> catch-all "and the rest"
        (None, Zone.EXCLUDED),  # no country data at all -> excluded, not zone 3
    ],
)
def test_zone_of(country_code, expected):
    assert zones_mod.zone_of(country_code, zones_file=ZONES_FILE) == expected


def test_egypt_and_saudi_arabia_always_excluded():
    assert zones_mod.zone_of("EG", zones_file=ZONES_FILE) == Zone.EXCLUDED
    assert zones_mod.zone_of("SA", zones_file=ZONES_FILE) == Zone.EXCLUDED


def test_egypt_and_saudi_arabia_excluded_even_if_placed_in_an_allowed_zone(tmp_path):
    """Regression guard: even if someone edits zones.yaml to list EG/SA under
    zone_2, the hardcoded exclusion in zones.py must still win.
    """
    bad_zones_file = tmp_path / "zones.yaml"
    bad_zones_file.write_text("zone_2:\n  - EG\n  - SA\n", encoding="utf-8")

    assert zones_mod.zone_of("EG", zones_file=bad_zones_file) == Zone.EXCLUDED
    assert zones_mod.zone_of("SA", zones_file=bad_zones_file) == Zone.EXCLUDED


@pytest.mark.parametrize(
    "zone,expected",
    [
        (Zone.ZONE_1, True),
        (Zone.ZONE_2, True),
        (Zone.ZONE_3, False),
        (Zone.EXCLUDED, False),
    ],
)
def test_is_allowed_zone(zone, expected):
    assert zones_mod.is_allowed_zone(zone) is expected
