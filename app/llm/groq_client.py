import json
import time
import httpx
from app.config import Settings
from app.llm.base import LLMError
from app.schemas import ScenarioRequest


class GroqClient:
    def __init__(self, settings: Settings):
        if not settings.groq_api_key:
            raise LLMError("GROQ_API_KEY is required for Groq provider")
        self.settings = settings

    def interpret(self, request: ScenarioRequest, validation_error: str | None = None) -> list[dict]:
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": _system_prompt(validation_error)},
                {"role": "user", "content": json.dumps({
                    "battery": request.battery.model_dump(),
                    "operator_notes": request.operator_notes,
                }, ensure_ascii=False)},
            ],
            "temperature": self.settings.llm_temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "directive_interpretations",
                    "strict": True,
                    "schema": _response_schema(),
                },
            },
        }
        last_exc: Exception | None = None
        attempts = max(1, self.settings.llm_max_retries + 2)
        for attempt in range(attempts):
            try:
                response = httpx.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.settings.llm_timeout_s,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                break
            except Exception as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(0.75 * (attempt + 1))
                    continue
                raise LLMError("Groq interpretation failed") from last_exc

        if isinstance(parsed, dict) and "items" in parsed:
            parsed = parsed["items"]
        if not isinstance(parsed, list):
            raise LLMError("Groq returned non-list JSON")
        return parsed


def _system_prompt(validation_error: str | None) -> str:
    retry = f"\nPrevious validation error: {validation_error}\nFix the output." if validation_error else ""
    return f"""You convert campus operator notes into machine-checkable energy directives.
Return exactly one interpretation per note.

Allowed directive_type values:
solar_reduction, minimum_battery_reserve, no_charge_window, no_discharge_window, max_grid_window, no_op.

Rules:
- note_index must match the input note index.
- Use no_op for irrelevant notes.
- Do not invent demand, solar, tariff, battery values, or unsupported directive types.
- Time windows are start-inclusive and end-exclusive. 1 PM to 3 PM means [13,14].
- hours must be unique integers 0 through 23 in ascending order.
- solar_reduction factor is usable fraction remaining.
- "80% reduction" means factor 0.2.
- "25% usable" means factor 0.25.
- Percent battery reserve must be computed from battery.capacity_kwh.
- no_op must use applies false and structured_adjustment null.
- Every other directive must use applies true.
{retry}"""


def _response_schema() -> dict:
    adjustment = {
        "type": ["object", "null"],
        "properties": {
            "hours": {"type": "array", "items": {"type": "integer"}},
            "factor": {"type": ["number", "null"]},
            "minimum_energy_kwh": {"type": ["number", "null"]},
            "max_grid_kwh": {"type": ["number", "null"]},
        },
        "required": ["hours", "factor", "minimum_energy_kwh", "max_grid_kwh"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "note_index": {"type": "integer"},
                        "applies": {"type": "boolean"},
                        "directive_type": {
                            "type": "string",
                            "enum": [
                                "solar_reduction",
                                "minimum_battery_reserve",
                                "no_charge_window",
                                "no_discharge_window",
                                "max_grid_window",
                                "no_op",
                            ],
                        },
                        "structured_adjustment": adjustment,
                        "explanation": {"type": "string"},
                    },
                    "required": [
                        "note_index",
                        "applies",
                        "directive_type",
                        "structured_adjustment",
                        "explanation",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
