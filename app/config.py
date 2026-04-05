from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

class Settings(BaseSettings):
    secret_key: str = "changeme-secret"
    panel_secret: str = ""
    admin_secret: str = ""
    auth_config_file: str = "app/auth/rbac_config.json"
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

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def resolved_templates_dir(self) -> str:
        path = Path(self.templates_dir)
        if not path.is_absolute():
            path = self.project_root / path
        return str(path)

    @property
    def resolved_output_dir(self) -> str:
        path = Path(self.output_dir)
        if not path.is_absolute():
            path = self.project_root / path
        return str(path)

    @property
    def resolved_auth_config_file(self) -> str:
        path = Path(self.auth_config_file)
        if not path.is_absolute():
            path = self.project_root / path
        return str(path)

@lru_cache
def get_settings() -> Settings:
    return Settings()
