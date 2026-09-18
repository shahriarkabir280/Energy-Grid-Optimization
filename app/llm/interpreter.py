from app.config import Settings
from app.guardrails import GuardrailError, validate_directives
from app.llm.base import LLMClient, LLMError
from app.llm.gemini_client import GeminiClient
from app.llm.groq_client import GroqClient
from app.llm.rule_client import RuleClient
from app.schemas import DirectiveInterpretation, ScenarioRequest


class FallbackClient:
    def __init__(self, clients: list[LLMClient]):
        if not clients:
            raise LLMError("no fallback LLM clients are configured")
        self.clients = clients

    def interpret(self, request: ScenarioRequest, validation_error: str | None = None) -> list[dict]:
        last_exc: Exception | None = None
        for client in self.clients:
            try:
                return client.interpret(request, validation_error=validation_error)
            except Exception as exc:
                last_exc = exc
        raise LLMError("all configured LLM providers failed") from last_exc


def build_client(settings: Settings) -> LLMClient:
    provider = settings.llm_provider.lower()
    if provider == "auto":
        clients: list[LLMClient] = []
        for item in settings.llm_provider_fallbacks.split(","):
            name = item.strip().lower()
            if not name:
                continue
            try:
                clients.append(_build_single_client(settings, name))
            except LLMError:
                continue
        return FallbackClient(clients)
    return _build_single_client(settings, provider)


def _build_single_client(settings: Settings, provider: str) -> LLMClient:
    if provider == "rule":
        return RuleClient()
    if provider == "gemini":
        return GeminiClient(settings)
    if provider == "groq":
        return GroqClient(settings)
    raise LLMError(f"unsupported LLM_PROVIDER: {settings.llm_provider}")


def interpret_with_guardrails(request: ScenarioRequest, client: LLMClient, max_retries: int) -> list[DirectiveInterpretation]:
    validation_error: str | None = None
    attempts = max(1, max_retries + 1)
    for _ in range(attempts):
        raw = client.interpret(request, validation_error=validation_error)
        try:
            return validate_directives(raw, len(request.operator_notes), request.battery)
        except GuardrailError as exc:
            validation_error = str(exc)
    raise LLMError(f"LLM output failed validation: {validation_error}")
