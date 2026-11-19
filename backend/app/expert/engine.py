from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from typing import Any

import yaml

KB_DIRECTORY = Path(__file__).resolve().parent
_ALLOWED_FACTS = {
    "moisture_category", "rain_category", "hot", "crop_stage", "soil_moisture_pct",
    "rain_forecast_mm_24h", "temp_c", "humidity_pct", "recent_fungal_diagnosis",
    "action", "duration_level",
}
_ALLOWED_OPERATORS = {"gt", "gte", "lt", "lte", "eq", "in"}
_ALLOWED_STAGES = {"Seedling", "Vegetative", "Flowering", "Fruiting"}
_ALLOWED_DURATIONS = {"normal", "increased", "short", "low_volume"}


@dataclass(frozen=True)
class IrrigationInputs:
    soil_moisture_pct: float
    rain_forecast_mm_24h: float | None
    temp_c: float
    humidity_pct: float
    crop_stage: str
    recent_diagnosis_label: str | None = None
    recent_diagnosis_ts: datetime | None = None
    recent_fungal_diagnosis: bool | None = None
    now: datetime | None = None


def load_builtin_knowledge_base(version: str = "v2") -> dict[str, Any]:
    if version not in {"v1", "v2"}:
        raise ValueError(f"Unknown packaged irrigation knowledge base version: {version}")
    path = KB_DIRECTORY / f"irrigation_kb_{version}.yaml"
    return parse_knowledge_base(path.read_text(encoding="utf-8"))


def _number(value: Any, name: str, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"Knowledge-base threshold {name} must be a finite number.")
    numeric = float(value)
    if minimum is not None and numeric < minimum:
        raise ValueError(f"Knowledge-base threshold {name} must be at least {minimum}.")
    if maximum is not None and numeric > maximum:
        raise ValueError(f"Knowledge-base threshold {name} must be at most {maximum}.")
    return numeric


def parse_knowledge_base(yaml_text: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Knowledge base YAML is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Knowledge base must be a mapping.")
    if not isinstance(data.get("version", "custom"), str):
        raise ValueError("Knowledge-base version must be a string.")

    thresholds = data.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("Knowledge base must contain a thresholds mapping.")
    moisture = thresholds.get("moisture")
    rain = thresholds.get("rain")
    if not isinstance(moisture, dict) or not isinstance(rain, dict):
        raise ValueError("Knowledge base must define moisture and rain thresholds.")
    low = _number(moisture.get("low_below_pct"), "moisture.low_below_pct", 0, 100)
    medium = _number(moisture.get("medium_through_pct"), "moisture.medium_through_pct", low, 100)
    none = _number(rain.get("none_below_mm"), "rain.none_below_mm", 0)
    light = _number(rain.get("light_through_mm"), "rain.light_through_mm", none)
    _number(thresholds.get("hot_above_c"), "hot_above_c")
    _number(thresholds.get("fungal_diagnosis_within_days"), "fungal_diagnosis_within_days", 0)
    labels = thresholds.get("fungal_labels")
    if not isinstance(labels, list) or not labels or not all(isinstance(label, str) and label.strip() for label in labels):
        raise ValueError("Knowledge base must define a non-empty fungal_labels list of strings.")
    if medium < low or light < none:
        raise ValueError("Knowledge-base category thresholds must be ordered from low to high.")

    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("Knowledge base must contain a non-empty rules list.")
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or not rule["id"].strip():
            raise ValueError("Each rule must have a non-empty string id.")
        if rule["id"] in seen:
            raise ValueError(f"Duplicate rule id: {rule['id']}.")
        seen.add(rule["id"])
        if type(rule.get("priority")) is not int:
            raise ValueError(f"Rule {rule['id']} must have an integer priority.")
        conditions = rule.get("conditions")
        action = rule.get("action")
        if not isinstance(conditions, dict) or not conditions:
            raise ValueError(f"Rule {rule['id']} must have a non-empty conditions mapping.")
        if not isinstance(action, dict):
            raise ValueError(f"Rule {rule['id']} must have an action mapping.")
        for key, expected in conditions.items():
            if key not in _ALLOWED_FACTS:
                raise ValueError(f"Rule {rule['id']} uses unsupported fact {key!r}.")
            values = expected.items() if isinstance(expected, dict) else [("eq", expected)]
            if isinstance(expected, dict) and (not expected or not set(expected).issubset(_ALLOWED_OPERATORS)):
                raise ValueError(f"Rule {rule['id']} uses an unsupported comparison operator.")
            for operator, value in values:
                if operator == "in":
                    if not isinstance(value, list) or not value:
                        raise ValueError(f"Rule {rule['id']} comparison 'in' requires a non-empty list.")
                elif operator in {"gt", "gte", "lt", "lte"}:
                    _number(value, f"{rule['id']}.{key}")
            if key in {"action", "duration_level", "crop_stage", "moisture_category", "rain_category", "hot", "recent_fungal_diagnosis"} and isinstance(expected, dict):
                raise ValueError(f"Rule {rule['id']} fact {key} requires a direct value, not a comparison mapping.")
            if key == "action" and (not isinstance(expected, str) or expected not in {"ON", "OFF"}):
                raise ValueError(f"Rule {rule['id']} action condition must be the string ON or OFF.")
            if key == "duration_level" and (not isinstance(expected, str) or expected not in _ALLOWED_DURATIONS):
                raise ValueError(f"Rule {rule['id']} has an invalid duration condition.")
            if key == "crop_stage" and (not isinstance(expected, str) or expected not in _ALLOWED_STAGES):
                raise ValueError(f"Rule {rule['id']} has an invalid crop-stage condition.")
            if key == "moisture_category" and (not isinstance(expected, str) or expected not in {"low", "medium", "high"}):
                raise ValueError(f"Rule {rule['id']} has an invalid moisture-category condition.")
            if key == "rain_category" and (not isinstance(expected, str) or expected not in {"none", "light", "heavy", "unknown"}):
                raise ValueError(f"Rule {rule['id']} has an invalid rain-category condition.")
            if key in {"hot", "recent_fungal_diagnosis"} and type(expected) is not bool:
                raise ValueError(f"Rule {rule['id']} fact {key} must be boolean.")
            if key in {"soil_moisture_pct", "rain_forecast_mm_24h", "temp_c", "humidity_pct"} and not isinstance(expected, dict):
                _number(expected, f"{rule['id']}.{key}")
        updates = action.get("set", {})
        if not isinstance(updates, dict):
            raise ValueError(f"Rule {rule['id']} action.set must be a mapping.")
        if set(action) - {"set", "advisory"}:
            raise ValueError(f"Rule {rule['id']} has an unsupported action property.")
        for key, value in updates.items():
            if key == "action" and (not isinstance(value, str) or value not in {"ON", "OFF"}):
                raise ValueError(f"Rule {rule['id']} action must be the string ON or OFF.")
            if key == "duration_level" and (not isinstance(value, str) or value not in _ALLOWED_DURATIONS):
                raise ValueError(f"Rule {rule['id']} has an invalid duration level.")
            if key not in {"action", "duration_level"}:
                raise ValueError(f"Rule {rule['id']} sets unsupported fact {key!r}.")
        if not updates and not action.get("advisory"):
            raise ValueError(f"Rule {rule['id']} must set a fact or provide an advisory.")
        if "advisory" in action and not isinstance(action["advisory"], str):
            raise ValueError(f"Rule {rule['id']} advisory must be a string.")
        if "explanation" in rule and not isinstance(rule["explanation"], str):
            raise ValueError(f"Rule {rule['id']} explanation must be a string.")
    data.setdefault("version", "custom")
    return data


def _recent_fungal_diagnosis(inputs: IrrigationInputs, thresholds: dict[str, Any], now: datetime) -> bool:
    if inputs.recent_fungal_diagnosis is not None:
        return inputs.recent_fungal_diagnosis
    if inputs.recent_diagnosis_label is None or inputs.recent_diagnosis_ts is None:
        return False
    diagnosis_ts = inputs.recent_diagnosis_ts
    if diagnosis_ts.tzinfo is None:
        diagnosis_ts = diagnosis_ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = now - diagnosis_ts
    if age < timedelta(0) or age > timedelta(days=float(thresholds["fungal_diagnosis_within_days"])):
        return False
    labels = {str(label).strip().casefold() for label in thresholds.get("fungal_labels", [])}
    return inputs.recent_diagnosis_label.strip().casefold() in labels


def _compare(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        for operator, value in expected.items():
            try:
                if operator == "gt" and not actual > value:
                    return False
                if operator == "gte" and not actual >= value:
                    return False
                if operator == "lt" and not actual < value:
                    return False
                if operator == "lte" and not actual <= value:
                    return False
                if operator == "eq" and not actual == value:
                    return False
                if operator == "in" and actual not in value:
                    return False
                if operator not in {"gt", "gte", "lt", "lte", "eq", "in"}:
                    raise ValueError(f"Unsupported rule comparison operator: {operator}")
            except TypeError:
                return False
        return True
    return actual == expected


def _matches(conditions: dict[str, Any], facts: dict[str, Any]) -> bool:
    return all(key in facts and _compare(facts[key], expected) for key, expected in conditions.items())


def evaluate_irrigation(inputs: IrrigationInputs, knowledge_base: dict[str, Any], version: str | None = None) -> dict[str, Any]:
    kb = parse_knowledge_base(yaml.safe_dump(knowledge_base, sort_keys=False))
    thresholds = kb["thresholds"]
    moisture = inputs.soil_moisture_pct
    moisture_thresholds = thresholds["moisture"]
    if moisture < float(moisture_thresholds["low_below_pct"]):
        moisture_category = "low"
    elif moisture <= float(moisture_thresholds["medium_through_pct"]):
        moisture_category = "medium"
    else:
        moisture_category = "high"

    rain = inputs.rain_forecast_mm_24h
    rain_thresholds = thresholds["rain"]
    if rain is None:
        rain_category = "unknown"
    elif rain < float(rain_thresholds["none_below_mm"]):
        rain_category = "none"
    elif rain <= float(rain_thresholds["light_through_mm"]):
        rain_category = "light"
    else:
        rain_category = "heavy"

    now = inputs.now or datetime.now(timezone.utc)
    recent_fungal = _recent_fungal_diagnosis(inputs, thresholds, now)
    facts: dict[str, Any] = {
        "moisture_category": moisture_category,
        "rain_category": rain_category,
        "hot": inputs.temp_c > float(thresholds["hot_above_c"]),
        "crop_stage": inputs.crop_stage,
        "soil_moisture_pct": inputs.soil_moisture_pct,
        "rain_forecast_mm_24h": rain,
        "temp_c": inputs.temp_c,
        "humidity_pct": inputs.humidity_pct,
        "recent_fungal_diagnosis": recent_fungal,
        "action": "OFF",
        "duration_level": "normal",
    }
    rules = sorted(kb["rules"], key=lambda rule: (rule["priority"], rule["id"]))
    fired: list[str] = []
    explanations: list[str] = []
    advisories: list[str] = []
    fact_priorities: dict[str, int] = {}
    for _ in range(len(rules) + 1):
        changed = False
        for rule in rules:
            if rule["id"] in fired or not _matches(rule["conditions"], facts):
                continue
            action = rule["action"]
            updates = action.get("set", {})
            action_update = updates.get("action")
            conflicts = (
                action_update is not None
                and "action" in fact_priorities
                and facts["action"] != action_update
                and fact_priorities["action"] <= rule["priority"]
            )
            if conflicts:
                continue
            fired.append(rule["id"])
            explanations.append(str(rule.get("explanation", f"Rule {rule['id']} fired.")))
            facts.update(updates)
            if action_update is not None:
                fact_priorities["action"] = min(fact_priorities.get("action", rule["priority"]), rule["priority"])
            advisory = action.get("advisory")
            if advisory:
                advisories.append(str(advisory))
            changed = True
        if not changed:
            break

    if fired:
        explanation = " ".join(explanations)
        if advisories:
            explanation = f"{explanation} Advisory: {' '.join(advisories)}"
        needs_review = False
        decision_type = "structured"
    else:
        explanation = "The knowledge base has no rule for this case; irrigation is off pending review."
        needs_review = True
        decision_type = "semi-structured"

    serialized_inputs = asdict(inputs)
    if serialized_inputs["now"] is not None:
        serialized_inputs["now"] = serialized_inputs["now"].isoformat()
    if serialized_inputs["recent_diagnosis_ts"] is not None:
        serialized_inputs["recent_diagnosis_ts"] = serialized_inputs["recent_diagnosis_ts"].isoformat()
    serialized_inputs.update(
        moisture_category=moisture_category,
        rain_category=rain_category,
        hot=facts["hot"],
        recent_fungal_diagnosis=recent_fungal,
    )
    return {
        "kb_version": version or str(kb.get("version", "custom")),
        "inputs": serialized_inputs,
        "action": facts["action"],
        "duration_level": facts["duration_level"],
        "fired_rule_ids": fired,
        "explanation": explanation,
        "needs_review": needs_review,
        "decision_type": decision_type,
        "advisories": advisories,
    }
