from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from reviewerfinder.models import Zone

# Hardcoded, unconditional exclusions. These take precedence over whatever is
# in zones.yaml so that editing the yaml alone can never accidentally let
# these countries through.
_HARD_EXCLUDED_COUNTRIES = {"EG", "SA"}


@lru_cache(maxsize=1)
def _load_zone_map(zones_file: Path) -> dict[str, Zone]:
    with open(zones_file, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    mapping: dict[str, Zone] = {}
    for zone_key, zone_enum in (
        ("zone_1", Zone.ZONE_1),
        ("zone_2", Zone.ZONE_2),
        ("zone_3", Zone.ZONE_3),
    ):
        for country_code in raw.get(zone_key, []) or []:
            mapping[country_code.upper()] = zone_enum
    return mapping


def zone_of(country_code: str | None, zones_file: Path | None = None) -> Zone:
    """Map an ISO 3166-1 alpha-2 country code to a trust zone.

    Egypt and Saudi Arabia are excluded unconditionally regardless of the
    zones.yaml contents. Any country not explicitly listed in zones.yaml
    ("and the rest") defaults to ZONE_3 rather than an opaque EXCLUDED
    bucket -- it's never invited either way, but this keeps the stored
    zone and fail_reasons accurate for unlisted countries.
    """
    if not country_code:
        return Zone.EXCLUDED

    code = country_code.upper()
    if code in _HARD_EXCLUDED_COUNTRIES:
        return Zone.EXCLUDED

    if zones_file is None:
        from config.settings import ZONES_FILE

        zones_file = ZONES_FILE

    return _load_zone_map(zones_file).get(code, Zone.ZONE_3)


def is_allowed_zone(zone: Zone) -> bool:
    return zone in (Zone.ZONE_1, Zone.ZONE_2)
