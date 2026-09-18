from dataclasses import dataclass, field
from .schemas import DirectiveInterpretation, ScenarioRequest


@dataclass
class AppliedDirectives:
    solar_factor: list[float] = field(default_factory=lambda: [1.0] * 24)
    minimum_reserve: list[float] = field(default_factory=lambda: [0.0] * 24)
    no_charge: set[int] = field(default_factory=set)
    no_discharge: set[int] = field(default_factory=set)
    max_grid: list[float | None] = field(default_factory=lambda: [None] * 24)


def apply_directives(request: ScenarioRequest, directives: list[DirectiveInterpretation]) -> AppliedDirectives:
    applied = AppliedDirectives()
    applied.minimum_reserve = [request.battery.minimum_energy_kwh] * 24

    for item in directives:
        adj = item.structured_adjustment or {}
        dtype = item.directive_type
        if dtype == "no_op":
            continue
        hours = adj.get("hours", [])
        if dtype == "solar_reduction":
            factor = float(adj["factor"])
            for h in hours:
                applied.solar_factor[h] = min(applied.solar_factor[h], factor)
        elif dtype == "minimum_battery_reserve":
            reserve = float(adj["minimum_energy_kwh"])
            for h in hours:
                applied.minimum_reserve[h] = max(applied.minimum_reserve[h], reserve)
        elif dtype == "no_charge_window":
            applied.no_charge.update(hours)
        elif dtype == "no_discharge_window":
            applied.no_discharge.update(hours)
        elif dtype == "max_grid_window":
            cap = float(adj["max_grid_kwh"])
            for h in hours:
                current = applied.max_grid[h]
                applied.max_grid[h] = cap if current is None else min(current, cap)
    return applied
