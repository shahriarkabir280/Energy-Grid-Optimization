import json
from app.config import Settings
from app.llm.base import LLMError
from app.schemas import ScenarioRequest


class GeminiClient:
    def __init__(self, settings: Settings):
        if not settings.llm_api_key:
            raise LLMError("LLM_API_KEY is required for Gemini provider")
        try:
            from google import genai
        except Exception as exc:
            raise LLMError("google-genai package is not installed") from exc
        self.settings = settings
        self.client = genai.Client(api_key=settings.llm_api_key)

    def interpret(self, request: ScenarioRequest, validation_error: str | None = None) -> list[dict]:
        prompt = _build_prompt(request, validation_error)
        models = [self.settings.llm_model]
        models.extend(
            m.strip()
            for m in self.settings.llm_fallback_models.split(",")
            if m.strip() and m.strip() != self.settings.llm_model
        )
        last_exc: Exception | None = None
        for model in models:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "temperature": self.settings.llm_temperature,
                        "response_mime_type": "application/json",
                    },
                )
                text = response.text or ""
                parsed = json.loads(text)
                if not isinstance(parsed, list):
                    raise LLMError("Gemini returned non-list JSON")
                return parsed
            except Exception as exc:
                last_exc = exc
                continue
        raise LLMError("Gemini interpretation failed") from last_exc


def _build_prompt(request: ScenarioRequest, validation_error: str | None) -> str:
    context = {
        "battery": request.battery.model_dump(),
        "operator_notes": request.operator_notes,
    }
    retry = f"\nPrevious validation error: {validation_error}\nFix the output.\n" if validation_error else ""
    return f"""
You convert campus operator notes into machine-checkable energy directives.
Return JSON only: an array with exactly one object per note.

Allowed directive_type values:
- solar_reduction: structured_adjustment {{"hours":[int], "factor": number}}
- minimum_battery_reserve: structured_adjustment {{"hours":[int], "minimum_energy_kwh": number}}
- no_charge_window: structured_adjustment {{"hours":[int]}}
- no_discharge_window: structured_adjustment {{"hours":[int]}}
- max_grid_window: structured_adjustment {{"hours":[int], "max_grid_kwh": number}}
- no_op: structured_adjustment null

Rules:
- note_index must match each input note index.
- Return entries in note_index order.
- Use no_op for irrelevant notes.
- Do not invent unsupported directive types.
- Time windows are start-inclusive and end-exclusive. 1 PM to 3 PM means [13,14].
- hours must be unique integers 0 through 23 in ascending order.
- For solar_reduction, factor is usable fraction remaining.
- "80% reduction" means factor 0.2.
- "25% usable" means factor 0.25.
- Percent battery reserve must be computed from battery.capacity_kwh.
- no_op must use applies false and structured_adjustment null.
- Every other directive must use applies true.
{retry}
Input JSON:
{json.dumps(context, ensure_ascii=False)}
"""
