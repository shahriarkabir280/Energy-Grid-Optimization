#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("response_json")
    args = parser.parse_args()
    data = json.loads(Path(args.response_json).read_text())
    required = {
        "scenario_id", "directive_interpretation", "hourly_plan",
        "total_grid_kwh", "total_cost_bdt", "peak_grid_kwh", "plan_summary",
    }
    missing = sorted(required - set(data))
    if missing:
        print(f"missing fields: {missing}")
        return 1
    if len(data["hourly_plan"]) != 24:
        print("hourly_plan must contain 24 entries")
        return 1
    print("response shape looks valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
