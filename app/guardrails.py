import math
from .schemas import BatteryConfig, DirectiveInterpretation


ALLOWED = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


class GuardrailError(ValueError):
    pass


def _hours(value) -> list[int]:
    if not isinstance(value, list):
        raise GuardrailError("hours must be a list")
    if any(not isinstance(h, int) for h in value):
        raise GuardrailError("hours must be integers")
    if any(h < 0 or h > 23 for h in value):
        raise GuardrailError("hours must be between 0 and 23")
    return sorted(set(value))


def _finite_number(value, name: str) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise GuardrailError(f"{name} must be finite number")
    return float(value)


def validate_directives(raw: list[dict], note_count: int, battery: BatteryConfig) -> list[DirectiveInterpretation]:
    if not isinstance(raw, list):
        raise GuardrailError("LLM output must be a list")
    if len(raw) != note_count:
        raise GuardrailError("LLM output must contain one entry per note")

    seen: set[int] = set()
    validated: list[DirectiveInterpretation] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise GuardrailError("each directive entry must be an object")
        note_index = entry.get("note_index")
        if not isinstance(note_index, int) or note_index < 0 or note_index >= note_count:
            raise GuardrailError("invalid note_index")
        if note_index in seen:
            raise GuardrailError("duplicate note_index")
        seen.add(note_index)

        dtype = entry.get("directive_type")
        if dtype not in ALLOWED:
            raise GuardrailError("unsupported directive_type")

        explanation = str(entry.get("explanation") or "")
        if dtype == "no_op":
            validated.append(DirectiveInterpretation(
                note_index=note_index,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation=explanation or "This note does not affect the energy schedule.",
            ))
            continue

        adj = entry.get("structured_adjustment")
        if not isinstance(adj, dict):
            raise GuardrailError("structured_adjustment must be object")
        hours = _hours(adj.get("hours"))
        if not hours:
            raise GuardrailError("directive hours cannot be empty")

        normalized: dict = {"hours": hours}
        if dtype == "solar_reduction":
            factor = _finite_number(adj.get("factor"), "factor")
            if factor < 0 or factor > 1:
                raise GuardrailError("factor must be between 0 and 1")
            normalized["factor"] = factor
        elif dtype == "minimum_battery_reserve":
            reserve = _finite_number(adj.get("minimum_energy_kwh"), "minimum_energy_kwh")
            if reserve < 0 or reserve > battery.capacity_kwh:
                raise GuardrailError("reserve must be between 0 and battery capacity")
            normalized["minimum_energy_kwh"] = reserve
        elif dtype == "max_grid_window":
            cap = _finite_number(adj.get("max_grid_kwh"), "max_grid_kwh")
            if cap < 0:
                raise GuardrailError("max_grid_kwh cannot be negative")
            normalized["max_grid_kwh"] = cap
        elif dtype not in {"no_charge_window", "no_discharge_window"}:
            raise GuardrailError("unsupported directive")

        validated.append(DirectiveInterpretation(
            note_index=note_index,
            applies=True,
            directive_type=dtype,
            structured_adjustment=normalized,
            explanation=explanation or f"Applied {dtype}.",
        ))

    if seen != set(range(note_count)):
        raise GuardrailError("note_index mapping must cover every note")
    return sorted(validated, key=lambda item: item.note_index)
