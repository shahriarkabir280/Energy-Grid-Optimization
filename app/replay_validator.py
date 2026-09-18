from .directives import AppliedDirectives
from .schemas import HourlyPlanEntry, ScenarioRequest


class ReplayError(ValueError):
    pass


TOL = 1e-4


def _close(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - b) <= tol


def replay_validate(request: ScenarioRequest, directives: AppliedDirectives, plan: list[HourlyPlanEntry]) -> None:
    if len(plan) != 24 or sorted(p.hour for p in plan) != list(range(24)):
        raise ReplayError("hourly_plan must contain exactly hours 0..23")
    hours = sorted(request.hours, key=lambda item: item.hour)
    plan = sorted(plan, key=lambda item: item.hour)
    energy_before = request.battery.initial_energy_kwh

    for h, (hour, row) in enumerate(zip(hours, plan)):
        effective_solar = hour.solar_kwh * directives.solar_factor[h]
        if row.grid_kwh < -TOL or row.solar_used_kwh < -TOL or row.battery_kwh < -TOL:
            raise ReplayError(f"negative energy at hour {h}")
        if row.solar_used_kwh - effective_solar > 0.01:
            raise ReplayError(f"solar overuse at hour {h}")
        if row.battery_action == "charge":
            charge, discharge = row.battery_kwh, 0.0
        elif row.battery_action == "discharge":
            charge, discharge = 0.0, row.battery_kwh
        else:
            charge, discharge = 0.0, 0.0
            if row.battery_kwh > 0.01:
                raise ReplayError(f"idle battery_kwh must be zero at hour {h}")

        if h in directives.no_charge and charge > 0.01:
            raise ReplayError(f"charge blocked at hour {h}")
        if h in directives.no_discharge and discharge > 0.01:
            raise ReplayError(f"discharge blocked at hour {h}")
        if charge - request.battery.max_charge_kwh_per_hour > 0.01:
            raise ReplayError(f"charge limit exceeded at hour {h}")
        if discharge - request.battery.max_discharge_kwh_per_hour > 0.01:
            raise ReplayError(f"discharge limit exceeded at hour {h}")
        if directives.max_grid[h] is not None and row.grid_kwh - directives.max_grid[h] > 0.01:
            raise ReplayError(f"grid cap exceeded at hour {h}")

        if not _close(row.grid_kwh + row.solar_used_kwh + discharge, hour.demand_kwh + charge):
            raise ReplayError(f"energy balance failed at hour {h}")

        expected_after = energy_before + charge - discharge
        if not _close(row.battery_energy_after_kwh, expected_after):
            raise ReplayError(f"battery transition failed at hour {h}")
        if row.battery_energy_after_kwh - request.battery.capacity_kwh > 0.01:
            raise ReplayError(f"battery capacity exceeded at hour {h}")
        if directives.minimum_reserve[h] - row.battery_energy_after_kwh > 0.01:
            raise ReplayError(f"battery reserve violated at hour {h}")
        energy_before = row.battery_energy_after_kwh

    if not _close(plan[-1].battery_energy_after_kwh, request.battery.initial_energy_kwh):
        raise ReplayError("end-of-day battery neutrality failed")


def calculate_totals(request: ScenarioRequest, plan: list[HourlyPlanEntry]) -> tuple[float, float, float]:
    hours = sorted(request.hours, key=lambda item: item.hour)
    plan = sorted(plan, key=lambda item: item.hour)
    total_grid = round(sum(p.grid_kwh for p in plan), 6)
    total_cost = round(sum(p.grid_kwh * h.tariff_bdt_per_kwh for p, h in zip(plan, hours)), 6)
    peak = round(max(p.grid_kwh for p in plan), 6)
    return total_grid, total_cost, peak
