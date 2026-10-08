import pytest

from reviewerfinder.pipeline import _validate_manual_keyword_sets


def test_valid_single_set():
    assert _validate_manual_keyword_sets([["a", "b"]]) == [["a", "b"]]


def test_valid_five_sets():
    sets = [[f"kw{i}"] for i in range(5)]
    assert _validate_manual_keyword_sets(sets) == sets


def test_strips_whitespace_and_drops_blanks():
    assert _validate_manual_keyword_sets([[" a ", "", "  b  "]]) == [["a", "b"]]


def test_rejects_zero_sets():
    with pytest.raises(ValueError):
        _validate_manual_keyword_sets([])


def test_rejects_more_than_five_sets():
    with pytest.raises(ValueError):
        _validate_manual_keyword_sets([["a"]] * 6)


def test_rejects_set_with_no_non_empty_keywords():
    with pytest.raises(ValueError):
        _validate_manual_keyword_sets([["   ", ""]])


def test_rejects_set_with_too_many_keywords():
    with pytest.raises(ValueError):
        _validate_manual_keyword_sets([[f"kw{i}" for i in range(9)]])
