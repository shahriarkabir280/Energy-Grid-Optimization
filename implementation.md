# GridWise LLM Implementation Plan

## Objective

Build a judge-ready HTTP API for the BUP CSE Fest 2026 GridWise preliminary.

The final system must:

- expose `GET /health`
- expose `POST /optimize-energy`
- use a real LLM to interpret `operator_notes`
- validate LLM output deterministically
- apply all valid directives to the optimizer
- return a valid 24-hour low-cost energy schedule
- include tests, Docker fallback, deployment instructions, README, and video support

Core pipeline:

```text
request
  -> schema validation
  -> LLM directive interpretation
  -> deterministic guardrails
  -> directive application
  -> LP optimizer
  -> replay validator
  -> exact JSON response
```

Rule-based interpretation is allowed only for local development and testing. The final submitted deployment must use a real LLM provider.

## Repository Layout

```text
/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── directives.py
│   ├── guardrails.py
│   ├── optimizer.py
│   ├── replay_validator.py
│   ├── summary.py
│   ├── errors.py
│   └── llm/
│       ├── __init__.py
│       ├── base.py
│       ├── interpreter.py
│       ├── rule_client.py
│       ├── gemini_client.py
│       └── openai_client.py
├── tests/
│   ├── conftest.py
│   ├── test_schema.py
│   ├── test_guardrails.py
│   ├── test_optimizer_public_cases.py
│   ├── test_replay_validator.py
│   └── test_api_public_cases.py
├── scripts/
│   ├── run_public_samples.py
│   └── validate_response.py
├── data/
│   └── public_sample_cases.json
├── Dockerfile
├── .dockerignore
├── .gitignore
├── .env.example
├── requirements.txt
└── README.md
```

Copy the provided public sample file into:

```text
data/public_sample_cases.json
```

## Team Responsibilities

### Member 1: API, Schemas, Integration

Owns:

- FastAPI app
- `GET /health`
- `POST /optimize-energy`
- Pydantic request and response schemas
- HTTP error mapping
- wiring the full pipeline together

Must implement:

- malformed JSON or invalid structure -> `400`
- semantically invalid but well-formed request -> `422`
- internal LLM/solver failure -> controlled `500`
- no stack traces or secrets in responses

### Member 2: LLM Interpretation

Owns:

- LLM client interface
- Gemini/OpenAI provider implementation
- rule-based dev client
- prompt design
- strict JSON parsing
- timeout and retry behavior

Final deployment should use:

```bash
LLM_PROVIDER=gemini
```

or:

```bash
LLM_PROVIDER=openai
```

Local development may use:

```bash
LLM_PROVIDER=rule
```

The rule client is only for development. A rule-only final submission does not satisfy the LLM requirement.

### Member 3: Guardrails, Directives, Optimizer

Owns:

- deterministic validation of LLM output
- directive normalization
- applying directives to optimizer constraints
- linear programming optimizer
- recalculating totals

Use `scipy.optimize.linprog` with method `highs`.

### Member 4: Testing, Docker, README, Deployment

Owns:

- public sample validation
- unit/integration tests
- Dockerfile
- deployment setup
- README
- 3-minute video outline
- final smoke tests from an external network

## API Contract

### `GET /health`

Response:

```json
{
  "status": "ok"
}
```

### `POST /optimize-energy`

Request must contain:

- `scenario_id`
- `operator_notes`: 1-3 non-empty strings
- `hours`: exactly 24 entries, unique hours `0..23`
- `battery`

Response must contain:

- `scenario_id`
- `directive_interpretation`
- `hourly_plan`
- `total_grid_kwh`
- `total_cost_bdt`
- `peak_grid_kwh`
- `plan_summary`

`directive_interpretation` must contain exactly one entry per operator note, sorted by `note_index`.

`hourly_plan` must contain exactly 24 entries, sorted by hour `0..23`.

## LLM Interpretation

The LLM must convert all operator notes into strict structured directives.

Supported directive types:

```text
solar_reduction
minimum_battery_reserve
no_charge_window
no_discharge_window
max_grid_window
no_op
```

Expected LLM output shape:

```json
[
  {
    "note_index": 0,
    "applies": true,
    "directive_type": "solar_reduction",
    "structured_adjustment": {
      "hours": [12, 13],
      "factor": 0.25
    },
    "explanation": "Solar availability is reduced during the maintenance window."
  }
]
```

Prompt requirements:

- Return JSON only.
- Return exactly one entry per note.
- Use only supported directive types.
- Use `no_op` for irrelevant notes.
- Do not invent demand, solar, tariff, or battery values.
- Time windows are start-inclusive and end-exclusive.
- Example: 1 PM to 3 PM means `[13, 14]`.
- For `solar_reduction`, `factor` means usable fraction remaining.
- "80% reduction" means `factor = 0.2`.
- "25% usable" means `factor = 0.25`.
- "50% of battery capacity" must be computed from the request battery capacity.

LLM runtime behavior:

- use one LLM call for all 1-3 notes
- set temperature to `0`
- enforce timeout with `LLM_TIMEOUT_S`
- retry once if output fails guardrails
- retry prompt should include the validation error
- after final failure, return controlled `500`; do not silently return a fake valid plan

## Guardrails

LLM output is untrusted until guardrails pass.

Guardrails must verify:

- directive type is one of the allowed values
- exactly one entry exists for each input note
- `note_index` is a bijection over `0..N-1`
- hours are integers from `0..23`
- hours are unique and sorted ascending
- `solar_reduction.factor` is finite and between `0` and `1`
- `minimum_battery_reserve.minimum_energy_kwh` is finite, non-negative, and not above battery capacity
- `max_grid_window.max_grid_kwh` is finite and non-negative
- `no_op` uses `applies = false` and `structured_adjustment = null`
- every non-`no_op` directive uses `applies = true`
- every non-`no_op` directive has the exact required `structured_adjustment` shape

Safe normalization:

- sorted hours may be accepted after sorting
- duplicate hours may be deduped only if all values are otherwise valid
- wrong `applies` may be corrected based on `directive_type`

Unsafe output should trigger retry or controlled failure:

- unsupported directive type
- missing note mapping
- duplicate note mapping that cannot be repaired
- out-of-range hour
- invalid numeric values
- wrong structured shape

Do not invent constraints.

## Directive Application

Apply directives exactly as follows.

### `solar_reduction`

```text
effective_solar[h] = original_solar[h] * factor
```

### `minimum_battery_reserve`

```text
battery_energy_after[h] >= max(base_minimum_energy_kwh, directive_minimum_energy_kwh)
```

### `no_charge_window`

```text
charge[h] = 0
```

### `no_discharge_window`

```text
discharge[h] = 0
```

### `max_grid_window`

```text
grid[h] <= max_grid_kwh
```

### `no_op`

No optimizer change.

Overlap assumptions:

- multiple reserve directives on the same hour -> use maximum reserve
- multiple grid caps on the same hour -> use minimum cap
- multiple solar reductions on the same hour -> use lowest usable factor
- charge and discharge blocks can both apply to the same hour

Document these assumptions in README.

## Optimizer

Use a linear programming model.

Variables per hour:

```text
grid_kwh[h]
solar_used_kwh[h]
charge_kwh[h]
discharge_kwh[h]
```

Objective:

```text
minimize sum(grid_kwh[h] * tariff_bdt_per_kwh[h])
```

Required constraints:

- `grid_kwh[h] >= 0`
- `solar_used_kwh[h] >= 0`
- `charge_kwh[h] >= 0`
- `discharge_kwh[h] >= 0`
- `solar_used_kwh[h] <= effective_solar[h]`
- `charge_kwh[h] <= max_charge_kwh_per_hour`
- `discharge_kwh[h] <= max_discharge_kwh_per_hour`
- no-charge windows force `charge_kwh[h] = 0`
- no-discharge windows force `discharge_kwh[h] = 0`
- grid-cap windows force `grid_kwh[h] <= max_grid_kwh`
- battery energy after every hour is within active minimum reserve and capacity
- final battery energy equals initial battery energy

Energy balance every hour:

```text
grid_kwh[h] + solar_used_kwh[h] + discharge_kwh[h]
= demand_kwh[h] + charge_kwh[h]
```

Battery state:

```text
energy_after[h] = initial_energy
                  + sum(charge_kwh[0..h])
                  - sum(discharge_kwh[0..h])
```

Post-processing:

- remove floating-point dust below tolerance
- avoid simultaneous visible charge/discharge in emitted plan
- derive `battery_action` from charge/discharge magnitude
- sort hourly plan by hour
- recompute all totals from emitted `hourly_plan`

Totals:

```text
total_grid_kwh = sum(grid_kwh)
total_cost_bdt = sum(grid_kwh[h] * tariff[h])
peak_grid_kwh = max(grid_kwh)
```

Use absolute tolerance `0.01` for kWh and BDT comparisons.

If LP is infeasible or solver fails, return controlled error. Never return a partial invalid schedule.

## Replay Validator

Before returning a successful response, independently replay the final `hourly_plan`.

Validate:

- exactly 24 unique hours `0..23`
- all numeric values finite and non-negative
- solar usage does not exceed effective solar
- demand is met every hour
- energy balance holds every hour
- battery transition is correct
- battery stays within capacity and active reserve
- charge/discharge limits are respected
- no-charge/no-discharge windows are respected
- grid caps are respected
- final battery energy equals initial battery energy
- reported totals match recomputed totals

If replay fails, return controlled `500`.

## `plan_summary`

Generate `plan_summary` deterministically, not with another LLM call.

Mention:

- total grid energy
- total cost
- peak grid hour/value
- major active directives
- battery strategy in short human-readable form

Do not rely on LLM for `plan_summary`; the mandatory LLM use is for operator-note interpretation.

## Configuration

`.env.example`:

```bash
LLM_PROVIDER=gemini
LLM_API_KEY=
LLM_MODEL=gemini-1.5-flash
LLM_TIMEOUT_S=10
LLM_MAX_RETRIES=1
LLM_TEMPERATURE=0
PORT=8000
```

For OpenAI:

```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
```

For local development:

```bash
LLM_PROVIDER=rule
LLM_API_KEY=
```

## Dependencies

`requirements.txt` should pin versions before final submission.

Base dependencies:

```text
fastapi
uvicorn[standard]
pydantic
numpy
scipy
python-dotenv
httpx
pytest
```

Gemini dependency:

```text
google-genai
```

OpenAI dependency:

```text
openai
```

Use only the provider package actually needed for final deployment if image size or install time becomes an issue.

## Tests

### Schema Tests

Cover:

- missing required fields
- empty `scenario_id`
- zero notes
- more than three notes
- empty note string
- duplicate hour
- missing hour
- more than 24 hours
- invalid battery capacity
- initial energy outside battery bounds
- negative demand, solar, tariff, or limits

### Guardrail Tests

Cover:

- unsupported directive type
- bad `note_index`
- duplicate `note_index`
- missing note mapping
- unsorted hours
- duplicate hours
- out-of-range hours
- `solar_reduction.factor > 1`
- negative factor
- reserve above capacity
- negative grid cap
- `no_op` with non-null adjustment
- non-`no_op` with `applies = false`

### Optimizer Tests

Use all 10 public sample cases.

For each sample:

- feed expected directives into optimizer
- replay final schedule
- assert total cost within `0.01` of expected output
- assert total grid within `0.01`
- assert peak grid within `0.01`
- assert final battery energy equals initial energy

### API Tests

Cover:

- `/health` returns `{"status":"ok"}`
- all public samples with fake deterministic interpreter
- malformed JSON -> `400`
- structurally invalid request -> `400`
- semantically invalid request -> `422`
- simulated LLM timeout/failure -> controlled `500`
- invalid LLM output retries, then controlled failure

### Live Public Sample Script

`scripts/run_public_samples.py` should call a running service and validate:

- HTTP status
- response schema
- directive interpretation
- hourly replay validity
- total grid
- total cost
- peak grid

Command:

```bash
python scripts/run_public_samples.py --base-url http://localhost:8000
```

The script should print one pass/fail line per sample and exit non-zero if any sample fails.

## Docker

Dockerfile requirements:

- use `python:3.12-slim`
- install dependencies
- copy source
- run as non-root user
- bind to `0.0.0.0:$PORT`
- expose port `8000`
- include healthcheck on `/health`
- do not bake in secrets

`.dockerignore` must exclude:

```text
.env
.venv
.git
__pycache__
.pytest_cache
```

Local verification:

```bash
docker build -t gridwise .
docker run --env-file .env -p 8000:8000 gridwise
curl http://localhost:8000/health
```

Fallback image submission:

```bash
docker tag gridwise ghcr.io/YOUR_TEAM/gridwise:preli-2026
docker push ghcr.io/YOUR_TEAM/gridwise:preli-2026
```

README must include the exact pullable image reference and a verified `docker run` command.

## Deployment

Choose one simple public platform:

- Render
- Railway
- Fly.io

Deployment requirements:

- public base URL
- no login/VPN/manual approval
- service binds `0.0.0.0`
- `/health` works externally
- `/optimize-energy` works externally
- LLM API key configured as platform secret
- no key committed to repo

External verification:

```bash
curl https://YOUR_PUBLIC_URL/health
python scripts/run_public_samples.py --base-url https://YOUR_PUBLIC_URL
```

Localhost testing is not enough.

## README Requirements

README must include:

- problem summary
- architecture diagram
- LLM role
- guardrail explanation
- optimizer explanation
- replay validation explanation
- environment variables
- local setup commands
- run command
- `/health` curl example
- `/optimize-energy` curl example
- public sample test command
- Docker build/run instructions
- Docker fallback image pull/run instructions
- deployment notes
- model/provider used
- dependencies and library credits
- known limitations
- secret-handling note
- AI/tool credit line

Safe AI credit line:

```text
AI coding assistance was used during development. The final architecture, implementation, validation, and submission were reviewed and owned by the team.
```

## Three-Minute Video Outline

Target structure:

1. 20 seconds: problem summary
2. 40 seconds: API request and response
3. 50 seconds: LLM interpretation and deterministic guardrails
4. 50 seconds: optimizer and replay validator
5. 30 seconds: public sample test/demo
6. 30 seconds: deployment, Docker fallback, and reliability

The video is tie-break only, but it should clearly show the LLM -> guardrails -> optimizer flow.

## Security Requirements

Never commit:

- API keys
- `.env`
- tokens
- provider secrets
- passwords

Never return:

- stack traces
- raw provider errors containing sensitive metadata
- environment variables
- API keys

Never log:

- `LLM_API_KEY`
- full secret-bearing config
- raw authorization headers

Use synthetic challenge data only.

## Highest-Marks Priority Order

1. Exact API contract
2. Real LLM interpretation
3. Deterministic guardrails
4. Correct directive application
5. Valid energy schedule
6. Cost optimization
7. Low latency and reliability
8. Public deployment
9. Docker fallback
10. README reproducibility
11. 3-minute video

Do not optimize cost before correctness. Invalid schedules receive no optimization credit.

## Four-Hour Execution Plan

### 0:00-0:30

- scaffold FastAPI app
- add schemas
- add `/health`
- copy public samples into `data/public_sample_cases.json`
- create `.env.example`

### 0:30-1:30

- implement optimizer
- implement directive application
- implement replay validator
- test optimizer using expected directives from public samples

### 1:30-2:15

- implement guardrails
- implement rule client for development
- add schema/guardrail/replay tests
- make all public optimizer tests pass

### 2:15-3:00

- implement real Gemini or OpenAI client
- implement prompt and retry behavior
- run public samples with real LLM
- refine prompt until interpretations are stable

### 3:00-3:30

- write Dockerfile
- write README
- create deployment
- configure LLM key as secret

### 3:30-4:00

- run external endpoint tests
- push Docker fallback image
- record 3-minute video
- final smoke test
- submit endpoint, repo, Docker image, README, and video

## Final Submission Checklist

- [ ] `GET /health` returns `{"status":"ok"}`
- [ ] `POST /optimize-energy` accepts exact request schema
- [ ] deployed service uses real LLM provider, not rule-only mode
- [ ] one interpretation entry per operator note
- [ ] `no_op` semantics are correct
- [ ] all directive hours are sorted unique integers `0..23`
- [ ] solar reduction factor semantics are correct
- [ ] reserve/grid cap numeric semantics are correct
- [ ] all directives are applied before optimization
- [ ] 24-hour schedule passes replay validator
- [ ] final battery energy equals initial battery energy
- [ ] reported totals match recalculated totals
- [ ] public sample script passes locally
- [ ] public sample script passes against deployed URL
- [ ] Docker image builds and runs
- [ ] Docker fallback image is pushed with exact tag/digest
- [ ] README has local setup, env vars, model/provider, run command, curl examples, Docker, deployment, and limitations
- [ ] `.env` and secrets are not committed
- [ ] 3-minute video is recorded and accessible
- [ ] public endpoint remains reachable during evaluation
