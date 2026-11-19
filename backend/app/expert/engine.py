from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

KB_DIRECTORY = Path(__file__).resolve().parent


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


def parse_knowledge_base(yaml_text: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Knowledge base YAML is invalid: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("thresholds"), dict):
        raise ValueError("Knowledge base must contain a thresholds mapping.")
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("Knowledge base must contain a non-empty rules list.")
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
            raise ValueError("Each rule must have a string id.")
        if rule["id"] in seen:
            raise ValueError(f"Duplicate rule id: {rule['id']}.")
        seen.add(rule["id"])
        if not isinstance(rule.get("priority"), int):
            raise ValueError(f"Rule {rule['id']} must have an integer priority.")
        if not isinstance(rule.get("conditions"), dict) or not isinstance(rule.get("action"), dict):
            raise ValueError(f"Rule {rule['id']} must have conditions and action mappings.")
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
    for _ in range(len(rules) + 1):
        changed = False
        for rule in rules:
            if rule["id"] in fired or not _matches(rule["conditions"], facts):
                continue
            fired.append(rule["id"])
            explanations.append(str(rule.get("explanation", f"Rule {rule['id']} fired.")))
            action = rule["action"]
            updates = action.get("set", {})
            if not isinstance(updates, dict):
                raise ValueError(f"Rule {rule['id']} action.set must be a mapping.")
            facts.update(updates)
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
