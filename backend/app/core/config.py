"""Central configuration. All assumptions are overridable via .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GreenCloud AI 2.0"
    database_url: str = "sqlite:///./greencloud.db"
    secret_key: str = "dev-only-change-me"
    access_token_minutes: int = 60
    cors_origins: list[str] = ["http://localhost:5173"]
    default_pue: float = 1.58
    data_mode: str = "simulated"  # simulated | local | live
    artifacts_dir: str = "artifacts"
    rate_limit_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
