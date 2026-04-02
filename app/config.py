from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    secret_key: str = "changeme-secret"
    auth_username: str = "hr@megansoft.com"
    auth_password: str = "MeganSoft2026!"
    access_token_expire_minutes: int = 480

    llm_provider: str = "azure-openai"
    llm_model: str = "gpt-4.1"
    llm_max_completion_tokens: int = 4000
    llm_slow_log_threshold_seconds: float = 8.0
    openai_api_key: str = ""
    azure_openai_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-4o-mini"
    anthropic_api_key: str = ""

    use_ocr: bool = True
    database_url: str = "sqlite:///./hrms.db"
    allowed_origins: str = "http://localhost:4200,http://localhost:3000"

    templates_dir: str = "templates"
    output_dir: str = "output"

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache
def get_settings() -> Settings:
    return Settings()
