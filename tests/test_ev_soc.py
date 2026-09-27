import pytest

from custom_components.hems.measurements import Observation, collect


def test_ev_soc_source_owns_freshness_even_with_legacy_options():
    options = {"ev_soc_entity": "ev", "ev_soc_max_age": 60, "ev_soc_timestamp_entity": "missing"}
    sample, _ = collect(options, lambda entity: Observation(80, "%", 0) if entity == "ev" else None, 86400)
    assert sample["ev_soc_pct"] == 80
    assert "soc" not in sample  # Battery control still requires its own valid observations.


@pytest.mark.parametrize("value", ["unknown", "unavailable", -1, 101, "nan", True])
def test_invalid_ev_soc_is_still_omitted(value):
    sample, invalid = collect({"ev_soc_entity": "ev"}, lambda _: Observation(value, "%", 0), 86400)
    assert "ev_soc_pct" not in sample
    assert "ev_soc_pct" in invalid
