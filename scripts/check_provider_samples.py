#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.directives import apply_directives
from app.llm.interpreter import build_client, interpret_with_guardrails
from app.optimizer import optimize_schedule
from app.replay_validator import calculate_totals, replay_validate
from app.schemas import ScenarioRequest


def main() -> int:
    settings = get_settings()
    client = build_client(settings)
    cases = json.load(open("data/public_sample_cases.json"))["cases"]
    failed = 0
    print("provider", settings.llm_provider, "model", settings.llm_model)
    for case in cases:
        request = ScenarioRequest.model_validate(case["input"])
        expected = case["expected_output"]
        try:
            items = interpret_with_guardrails(request, client, settings.llm_max_retries)
            applied = apply_directives(request, items)
            plan = optimize_schedule(request, applied)
            replay_validate(request, applied, plan)
            total_grid, total_cost, peak = calculate_totals(request, plan)
            got = [(i.directive_type, i.structured_adjustment) for i in items]
            exp = [(i["directive_type"], i["structured_adjustment"]) for i in expected["directive_interpretation"]]
            ok = (
                got == exp
                and abs(total_cost - expected["total_cost_bdt"]) <= 0.01
                and abs(total_grid - expected["total_grid_kwh"]) <= 0.01
                and abs(peak - expected["peak_grid_kwh"]) <= 0.01
            )
            print(f"{case['id']}: {'PASS' if ok else 'FAIL'} cost={total_cost} grid={total_grid} peak={peak}")
            failed += 0 if ok else 1
        except Exception as exc:
            print(f"{case['id']}: ERROR {type(exc).__name__}: {exc}")
            failed += 1
        time.sleep(1.5)
    print("failed", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
