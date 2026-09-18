from app.directives import apply_directives
from app.guardrails import validate_directives
from app.optimizer import optimize_schedule
from app.replay_validator import calculate_totals, replay_validate
from app.schemas import ScenarioRequest


def test_optimizer_matches_public_case_costs(sample_cases):
    for case in sample_cases:
        request = ScenarioRequest.model_validate(case["input"])
        expected = case["expected_output"]
        directives = validate_directives(
            [d for d in expected["directive_interpretation"]],
            len(request.operator_notes),
            request.battery,
        )
        applied = apply_directives(request, directives)
        plan = optimize_schedule(request, applied)
        replay_validate(request, applied, plan)
        total_grid, total_cost, peak = calculate_totals(request, plan)
        assert abs(total_cost - expected["total_cost_bdt"]) <= 0.01, case["id"]
        assert abs(total_grid - expected["total_grid_kwh"]) <= 0.01, case["id"]
        assert abs(peak - expected["peak_grid_kwh"]) <= 0.01, case["id"]
