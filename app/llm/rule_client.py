import re
from app.schemas import ScenarioRequest


def _parse_time(raw: str) -> int:
    raw = raw.strip().lower()
    if raw == "noon":
        return 12
    if raw == "midnight":
        return 0
    match = re.search(r"(\d{1,2})(?::\d{2})?\s*(am|pm)?", raw)
    if not match:
        return 0
    value = int(match.group(1))
    suffix = match.group(2)
    if suffix == "pm" and value != 12:
        value += 12
    if suffix == "am" and value == 12:
        value = 0
    return value


def _window(text: str) -> list[int]:
    text = text.lower()
    time = r"(?:noon|midnight|\d{1,2}(?::\d{2})?\s*(?:am|pm)?)"
    patterns = [
        rf"from\s+({time})\s+(?:until|to|-)\s+({time})",
        rf"between\s+({time})\s+and\s+({time})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            start, end = _parse_time(match.group(1)), _parse_time(match.group(2))
            if end <= start and end <= 12:
                end += 12
            return list(range(max(0, start), min(24, end)))
    return []


def _number(text: str, default: float | None = None, unit: str | None = None) -> float | None:
    if unit == "percent":
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    elif unit == "kwh":
        match = re.search(r"(\d+(?:\.\d+)?)\s*kwh", text)
    else:
        match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else default


class RuleClient:
    """Development-only interpreter for local testing without an API key."""

    def interpret(self, request: ScenarioRequest, validation_error: str | None = None) -> list[dict]:
        output = []
        capacity = request.battery.capacity_kwh
        for idx, note in enumerate(request.operator_notes):
            text = note.lower()
            hours = _window(text)
            if any(w in text for w in ["solar", "pv", "panel"]):
                pct = _number(text, None, "percent")
                factor = 1.0
                if "half" in text:
                    factor = 0.5
                elif pct is not None:
                    if "reduction" in text or "drop" in text or "reduced" in text:
                        factor = max(0.0, min(1.0, 1.0 - pct / 100.0))
                    else:
                        factor = max(0.0, min(1.0, pct / 100.0))
                output.append({"note_index": idx, "applies": True, "directive_type": "solar_reduction",
                               "structured_adjustment": {"hours": hours or [12, 13], "factor": factor},
                               "explanation": "Rule-mode solar interpretation."})
            elif (
                "do not charge" in text
                or "no charge" in text
                or ("charging" in text and ("unavailable" in text or "disabled" in text))
                or ("charger" in text and "isolated" in text)
            ):
                output.append({"note_index": idx, "applies": True, "directive_type": "no_charge_window",
                               "structured_adjustment": {"hours": hours or [14, 15]},
                               "explanation": "Rule-mode no-charge interpretation."})
            elif (
                "do not discharge" in text
                or "no discharge" in text
                or "must not discharge" in text
                or ("discharge" in text and "unavailable" in text)
            ):
                output.append({"note_index": idx, "applies": True, "directive_type": "no_discharge_window",
                               "structured_adjustment": {"hours": hours or [18, 19]},
                               "explanation": "Rule-mode no-discharge interpretation."})
            elif "reserve" in text or "keep at least" in text or ("requires at least" in text and "battery" in text):
                value = _number(text, None, "kwh")
                pct = _number(text, None, "percent")
                if value is None:
                    value = request.battery.minimum_energy_kwh
                if "%" in text:
                    value = capacity * (pct or 0) / 100.0
                output.append({"note_index": idx, "applies": True, "directive_type": "minimum_battery_reserve",
                               "structured_adjustment": {"hours": hours or [18, 19, 20], "minimum_energy_kwh": value},
                               "explanation": "Rule-mode reserve interpretation."})
            elif "grid" in text or "feeder" in text or "transformer" in text or "import" in text:
                value = _number(text, 999999, "kwh")
                output.append({"note_index": idx, "applies": True, "directive_type": "max_grid_window",
                               "structured_adjustment": {"hours": hours or [18, 19, 20], "max_grid_kwh": value},
                               "explanation": "Rule-mode grid-cap interpretation."})
            else:
                output.append({"note_index": idx, "applies": False, "directive_type": "no_op",
                               "structured_adjustment": None,
                               "explanation": "Rule-mode no-op interpretation."})
        return output
