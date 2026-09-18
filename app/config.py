from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_provider: str = Field(default="rule", alias="LLM_PROVIDER")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    llm_model: str = Field(default="openai/gpt-oss-20b", alias="LLM_MODEL")
    llm_fallback_models: str = Field(default="gemini-3.1-flash-lite,gemini-flash-lite-latest,gemini-flash-latest", alias="LLM_FALLBACK_MODELS")
    llm_provider_fallbacks: str = Field(default="groq,gemini", alias="LLM_PROVIDER_FALLBACKS")
    llm_timeout_s: float = Field(default=10.0, alias="LLM_TIMEOUT_S")
    llm_max_retries: int = Field(default=1, alias="LLM_MAX_RETRIES")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    port: int = Field(default=8000, alias="PORT")

    model_config = {"env_file": ".env", "extra": "ignore", "populate_by_name": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()
