from __future__ import annotations


def country_filter_ok(
    country_code: str | None,
    *,
    allowed_countries: list[str] | None,
    excluded_countries: list[str] | None,
) -> tuple[bool, str | None]:
    """A per-search, user-supplied country filter -- distinct from the
    hardcoded Zone 1/2/3 + Egypt/Saudi-Arabia rules in zones.py/filters.py,
    which never change between searches. This lets a single search further
    restrict candidates to (or away from) specific countries, on top of
    those always-applied rules.

    Returns (passed, fail_reason); fail_reason is None when passed.

    - excluded_countries is checked first: a code appearing in both lists
      fails (deny always wins over allow).
    - allowed_countries, if given (non-empty), is a strict allow-list: a
      country not in it fails.
    - A missing country_code fails only if an allow-list was given (there's
      nothing to prove membership with); it passes untouched against a
      deny-list alone, since there's nothing to match.
    """
    allowed = {c.upper() for c in allowed_countries} if allowed_countries else None
    excluded = {c.upper() for c in excluded_countries} if excluded_countries else None

    if not country_code:
        if allowed:
            return False, "country_unknown_but_allow_list_set"
        return True, None

    code = country_code.upper()

    if excluded and code in excluded:
        return False, f"country_in_deny_list:{code}"

    if allowed and code not in allowed:
        return False, f"country_not_in_allow_list:{code}"

    return True, None
