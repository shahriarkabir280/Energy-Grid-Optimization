#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def close(a, b, tol=0.01):
    return abs(float(a) - float(b)) <= tol


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--samples", default="data/public_sample_cases.json")
    args = parser.parse_args()
    cases = json.loads(Path(args.samples).read_text())["cases"]
    failed = 0
    with httpx.Client(timeout=30) as client:
        for case in cases:
            response = client.post(f"{args.base_url.rstrip('/')}/optimize-energy", json=case["input"])
            if response.status_code != 200:
                print(f"{case['id']}: FAIL status={response.status_code} body={response.text[:200]}")
                failed += 1
                continue
            body = response.json()
            expected = case["expected_output"]
            ok = (
                len(body.get("hourly_plan", [])) == 24
                and close(body.get("total_cost_bdt", -1), expected["total_cost_bdt"])
                and close(body.get("total_grid_kwh", -1), expected["total_grid_kwh"])
                and close(body.get("peak_grid_kwh", -1), expected["peak_grid_kwh"])
            )
            print(f"{case['id']}: {'PASS' if ok else 'FAIL'} cost={body.get('total_cost_bdt')}")
            failed += 0 if ok else 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
