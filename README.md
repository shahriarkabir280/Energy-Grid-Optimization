# GridWise LLM

Judge-ready FastAPI service for the BUP CSE Fest 2026 GridWise preliminary.

## Architecture

```text
operator_notes + scenario
  -> real LLM interpretation
  -> deterministic guardrails
  -> directive application
  -> scipy LP optimizer
  -> replay validator
  -> exact JSON response
```

The final deployment should use `LLM_PROVIDER=auto` when both Groq and Gemini keys are available. It tries providers in `LLM_PROVIDER_FALLBACKS` order. `LLM_PROVIDER=rule` is only for local development without an API key.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set your key in `.env`:

```bash
LLM_PROVIDER=auto
LLM_PROVIDER_FALLBACKS=groq,gemini
LLM_API_KEY=your_key_here
GROQ_API_KEY=your_groq_key_here
LLM_MODEL=openai/gpt-oss-20b
LLM_FALLBACK_MODELS=gemini-3.1-flash-lite,gemini-flash-lite-latest,gemini-flash-latest
```

Do not commit `.env`.

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

Run public samples:

```bash
python scripts/run_public_samples.py --base-url http://localhost:8000
```

## Tests

```bash
pytest -q
```

## Docker

```bash
docker build -t gridwise .
docker run --env-file .env -p 8000:8000 gridwise
```

Submission image example:

```bash
docker tag gridwise ghcr.io/YOUR_TEAM/gridwise:preli-2026
docker push ghcr.io/YOUR_TEAM/gridwise:preli-2026
```

## Environment Variables

- `LLM_PROVIDER`: `auto`, `groq`, or `gemini` for final deployment, `rule` for local development
- `LLM_PROVIDER_FALLBACKS`: provider order used when `LLM_PROVIDER=auto`
- `LLM_API_KEY`: provider API key
- `GROQ_API_KEY`: Groq API key when using `LLM_PROVIDER=groq`
- `LLM_MODEL`: provider model name, for example `openai/gpt-oss-20b`
- `LLM_FALLBACK_MODELS`: comma-separated Gemini models to try if the primary model is unavailable
- `LLM_TIMEOUT_S`: intended provider timeout
- `LLM_MAX_RETRIES`: validation retry count
- `LLM_TEMPERATURE`: keep `0`
- `PORT`: service port

## Notes

The optimizer enforces energy balance, effective solar, battery bounds, charge/discharge limits, grid caps, and end-of-day battery neutrality. All totals are recalculated from the emitted `hourly_plan`.

AI coding assistance was used during development. The final architecture, implementation, validation, and submission were reviewed and owned by the team.
