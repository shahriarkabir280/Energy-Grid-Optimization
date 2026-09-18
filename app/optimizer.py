import numpy as np
from scipy.optimize import linprog
from .directives import AppliedDirectives
from .schemas import HourlyPlanEntry, ScenarioRequest


class OptimizerError(RuntimeError):
    pass


def _clean(value: float) -> float:
    if abs(value) < 1e-7:
        value = 0.0
    return round(float(value), 6)


def optimize_schedule(request: ScenarioRequest, directives: AppliedDirectives) -> list[HourlyPlanEntry]:
    hours = sorted(request.hours, key=lambda item: item.hour)
    b = request.battery
    n = 24
    # variable order: grid[0..23], solar[0..23], charge[0..23], discharge[0..23]
    grid = lambda h: h
    solar = lambda h: n + h
    charge = lambda h: 2 * n + h
    discharge = lambda h: 3 * n + h

    c = np.zeros(4 * n)
    for h, item in enumerate(hours):
        c[grid(h)] = item.tariff_bdt_per_kwh

    bounds: list[tuple[float, float | None]] = []
    for h in range(n):
        bounds.append((0, directives.max_grid[h]))
    for h, item in enumerate(hours):
        bounds.append((0, item.solar_kwh * directives.solar_factor[h]))
    for h in range(n):
        bounds.append((0, 0 if h in directives.no_charge else b.max_charge_kwh_per_hour))
    for h in range(n):
        bounds.append((0, 0 if h in directives.no_discharge else b.max_discharge_kwh_per_hour))

    a_eq = []
    b_eq = []
    for h, item in enumerate(hours):
        row = np.zeros(4 * n)
        row[grid(h)] = 1
        row[solar(h)] = 1
        row[discharge(h)] = 1
        row[charge(h)] = -1
        a_eq.append(row)
        b_eq.append(item.demand_kwh)

    row = np.zeros(4 * n)
    for h in range(n):
        row[charge(h)] = 1
        row[discharge(h)] = -1
    a_eq.append(row)
    b_eq.append(0)

    a_ub = []
    b_ub = []
    for h in range(n):
        # initial + cumulative charge - cumulative discharge <= capacity
        row = np.zeros(4 * n)
        for t in range(h + 1):
            row[charge(t)] = 1
            row[discharge(t)] = -1
        a_ub.append(row)
        b_ub.append(b.capacity_kwh - b.initial_energy_kwh)

        # -(initial + cumulative charge - cumulative discharge) <= -active_min
        row = np.zeros(4 * n)
        for t in range(h + 1):
            row[charge(t)] = -1
            row[discharge(t)] = 1
        a_ub.append(row)
        b_ub.append(b.initial_energy_kwh - directives.minimum_reserve[h])

    a_ub_arr = np.array(a_ub)
    b_ub_arr = np.array(b_ub)
    a_eq_arr = np.array(a_eq)
    b_eq_arr = np.array(b_eq)
    result = linprog(c, A_ub=a_ub_arr, b_ub=b_ub_arr, A_eq=a_eq_arr,
                     b_eq=b_eq_arr, bounds=bounds, method="highs")
    if not result.success:
        raise OptimizerError(f"optimizer failed: {result.message}")
    x = _minimize_peak_with_fixed_cost(c, result.fun, result.x, a_ub_arr, b_ub_arr, a_eq_arr, b_eq_arr, bounds, n)

    plan: list[HourlyPlanEntry] = []
    energy = b.initial_energy_kwh
    for h in range(n):
        ch = _clean(x[charge(h)])
        dis = _clean(x[discharge(h)])
        if ch > 1e-5 and dis > 1e-5:
            net = ch - dis
            ch = _clean(max(net, 0))
            dis = _clean(max(-net, 0))
        energy = _clean(energy + ch - dis)
        if ch > 1e-5:
            action, amount = "charge", ch
        elif dis > 1e-5:
            action, amount = "discharge", dis
        else:
            action, amount = "idle", 0.0
        plan.append(HourlyPlanEntry(
            hour=h,
            grid_kwh=_clean(x[grid(h)]),
            solar_used_kwh=_clean(x[solar(h)]),
            battery_action=action,
            battery_kwh=_clean(amount),
            battery_energy_after_kwh=energy,
        ))
    return plan


def _minimize_peak_with_fixed_cost(c, optimal_cost, fallback_x, a_ub, b_ub, a_eq, b_eq, bounds, n):
    """Pick the lowest-peak schedule among cost-optimal LP solutions."""
    old_vars = 4 * n
    total_vars = old_vars + 1
    peak_idx = old_vars

    c2 = np.zeros(total_vars)
    c2[peak_idx] = 1

    bounds2 = list(bounds) + [(0, None)]
    a_eq2 = np.pad(a_eq, ((0, 0), (0, 1)))

    rows = [np.pad(row, (0, 1)) for row in a_ub]
    rhs = list(b_ub)

    cost_row = np.zeros(total_vars)
    cost_row[:old_vars] = c
    rows.append(cost_row)
    rhs.append(optimal_cost + 1e-7)

    for h in range(n):
        row = np.zeros(total_vars)
        row[h] = 1
        row[peak_idx] = -1
        rows.append(row)
        rhs.append(0)

    result = linprog(c2, A_ub=np.array(rows), b_ub=np.array(rhs), A_eq=a_eq2,
                     b_eq=b_eq, bounds=bounds2, method="highs")
    if not result.success:
        return fallback_x
    return result.x[:old_vars]
