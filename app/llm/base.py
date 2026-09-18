from typing import Protocol
from app.schemas import ScenarioRequest


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def interpret(self, request: ScenarioRequest, validation_error: str | None = None) -> list[dict]:
        ...
