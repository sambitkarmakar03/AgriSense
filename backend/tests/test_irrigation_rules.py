from datetime import datetime, timedelta, timezone

import pytest

from app.expert.engine import IrrigationInputs, evaluate_irrigation, load_builtin_knowledge_base


SCENARIOS = [
    pytest.param(
        IrrigationInputs(20, 0, 39, 55, "Flowering"),
        "ON",
        "increased",
        ["IR-1", "IR-3"],
        False,
        id="monday-low-moisture-flowering-hot",
    ),
    pytest.param(
        IrrigationInputs(80, 15, 31, 55, "Vegetative"),
        "OFF",
        "normal",
        ["IR-2"],
        False,
        id="tuesday-heavy-rain",
    ),
    pytest.param(
        IrrigationInputs(45, 0, 37, 55, "Fruiting"),
        "OFF",
        "normal",
        [],
        True,
        id="wednesday-gap-case",
    ),
    pytest.param(
        IrrigationInputs(20, 5, 35, 55, "Seedling"),
        "OFF",
        "normal",
        [],
        True,
        id="thursday-gap-case",
    ),
]


@pytest.mark.parametrize("inputs,action,duration,fired,needs_review", SCENARIOS)
def test_all_golden_scenarios_kb_v1(inputs, action, duration, fired, needs_review):
    result = evaluate_irrigation(inputs, load_builtin_knowledge_base("v1"), "v1")
    assert result["action"] == action
    assert result["duration_level"] == duration
    assert result["fired_rule_ids"] == fired
    assert result["needs_review"] is needs_review
    assert result["decision_type"] == ("semi-structured" if needs_review else "structured")


@pytest.mark.parametrize(
    "inputs,action,duration,fired,needs_review",
    [
        SCENARIOS[0],
        SCENARIOS[1],
        pytest.param(SCENARIOS[2].values[0], "ON", "short", ["IR-4"], False, id="wednesday-ir-4"),
        pytest.param(SCENARIOS[3].values[0], "ON", "low_volume", ["IR-5"], False, id="thursday-ir-5"),
    ],
)
def test_all_golden_scenarios_kb_v2(inputs, action, duration, fired, needs_review):
    result = evaluate_irrigation(inputs, load_builtin_knowledge_base("v2"), "v2")
    assert result["action"] == action
    assert result["duration_level"] == duration
    assert result["fired_rule_ids"] == fired
    assert result["needs_review"] is needs_review
    assert result["decision_type"] == ("semi-structured" if needs_review else "structured")


def test_ir6_adds_conservative_watering_advisory_within_seven_days():
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    inputs = IrrigationInputs(
        20,
        0,
        28,
        85,
        "Vegetative",
        recent_diagnosis_label="Powdery Mildew",
        recent_diagnosis_ts=now - timedelta(days=6),
        now=now,
    )
    result = evaluate_irrigation(inputs, load_builtin_knowledge_base("v2"), "v2")
    assert result["action"] == "ON"
    assert result["fired_rule_ids"] == ["IR-1", "IR-6"]
    assert "prefer drip" in result["explanation"]


def test_ir6_does_not_fire_for_old_or_non_fungal_diagnosis():
    now = datetime(2026, 11, 19, tzinfo=timezone.utc)
    for label, days in [("Rust", 8), ("Healthy", 2)]:
        inputs = IrrigationInputs(
            20,
            0,
            28,
            85,
            "Vegetative",
            recent_diagnosis_label=label,
            recent_diagnosis_ts=now - timedelta(days=days),
            now=now,
        )
        result = evaluate_irrigation(inputs, load_builtin_knowledge_base("v2"), "v2")
        assert "IR-6" not in result["fired_rule_ids"]


def test_unknown_rain_forecast_falls_back_to_review():
    result = evaluate_irrigation(
        IrrigationInputs(20, None, 25, 40, "Vegetative"),
        load_builtin_knowledge_base("v2"),
        "v2",
    )
    assert result["action"] == "OFF"
    assert result["needs_review"] is True
    assert result["fired_rule_ids"] == []
