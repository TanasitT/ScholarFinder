from reviewerfinder.rules.country_filter import country_filter_ok


def test_no_lists_always_passes():
    assert country_filter_ok("DE", allowed_countries=None, excluded_countries=None) == (True, None)


def test_allow_list_contains_code_passes():
    assert country_filter_ok("DE", allowed_countries=["US", "DE"], excluded_countries=None) == (True, None)


def test_allow_list_missing_code_fails():
    passed, reason = country_filter_ok("FR", allowed_countries=["US", "DE"], excluded_countries=None)
    assert passed is False
    assert reason == "country_not_in_allow_list:FR"


def test_deny_list_contains_code_fails():
    passed, reason = country_filter_ok("EG", allowed_countries=None, excluded_countries=["EG"])
    assert passed is False
    assert reason == "country_in_deny_list:EG"


def test_deny_list_wins_over_allow_list():
    passed, reason = country_filter_ok(
        "EG", allowed_countries=["EG", "US"], excluded_countries=["EG"]
    )
    assert passed is False
    assert reason == "country_in_deny_list:EG"


def test_missing_country_fails_when_allow_list_set():
    passed, reason = country_filter_ok(None, allowed_countries=["US"], excluded_countries=None)
    assert passed is False
    assert reason == "country_unknown_but_allow_list_set"


def test_missing_country_passes_when_only_deny_list_set():
    assert country_filter_ok(None, allowed_countries=None, excluded_countries=["EG"]) == (True, None)


def test_codes_normalized_to_uppercase():
    assert country_filter_ok("de", allowed_countries=["DE"], excluded_countries=None) == (True, None)
    passed, reason = country_filter_ok("de", allowed_countries=None, excluded_countries=["de"])
    assert passed is False
    assert reason == "country_in_deny_list:DE"
