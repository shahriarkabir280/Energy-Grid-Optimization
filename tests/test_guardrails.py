import pytest
from app.guardrails import GuardrailError, validate_directives
from app.schemas import BatteryConfig


BATTERY = BatteryConfig(
    capacity_kwh=200,
    initial_energy_kwh=100,
    minimum_energy_kwh=40,
    max_charge_kwh_per_hour=50,
    max_discharge_kwh_per_hour=50,
)


def test_normalizes_no_op():
    result = validate_directives([{
        "note_index": 0,
        "applies": True,
        "directive_type": "no_op",
        "structured_adjustment": {"bad": True},
    }], 1, BATTERY)
    assert result[0].applies is False
    assert result[0].structured_adjustment is None


def test_rejects_bad_type():
    with pytest.raises(GuardrailError):
        validate_directives([{"note_index": 0, "directive_type": "bad"}], 1, BATTERY)


def test_rejects_out_of_range_hour():
    with pytest.raises(GuardrailError):
        validate_directives([{
            "note_index": 0,
            "directive_type": "no_charge_window",
            "structured_adjustment": {"hours": [25]},
        }], 1, BATTERY)


def test_sorts_and_dedupes_hours():
    result = validate_directives([{
        "note_index": 0,
        "directive_type": "no_charge_window",
        "structured_adjustment": {"hours": [3, 2, 2]},
    }], 1, BATTERY)
    assert result[0].structured_adjustment == {"hours": [2, 3]}
