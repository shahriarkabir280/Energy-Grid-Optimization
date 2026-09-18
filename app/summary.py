from .schemas import DirectiveInterpretation, HourlyPlanEntry


def build_summary(directives: list[DirectiveInterpretation], plan: list[HourlyPlanEntry], total_grid: float, total_cost: float, peak: float) -> str:
    active = [d.directive_type for d in directives if d.applies]
    peak_hour = max(plan, key=lambda item: item.grid_kwh).hour
    active_text = ", ".join(active) if active else "no active operator directives"
    return (
        f"Optimized 24-hour schedule uses {total_grid:.2f} kWh from grid at "
        f"{total_cost:.2f} BDT. Peak grid import is {peak:.2f} kWh at hour {peak_hour}. "
        f"Applied directives: {active_text}."
    )
