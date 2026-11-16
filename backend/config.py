from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    verify_token: str = "change-me"
    meta_app_secret: str = ""
    meta_access_token: str = ""
    instagram_account_id: str = ""
    graph_api_version: str = "v24.0"
    ai_provider: str = "none"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    allowed_sender_ids: str = ""
    view_once_enabled: bool = False
    view_once_debug_raw: bool = False
    view_once_retention_days: int = 30
    media_max_bytes: int = 15 * 1024 * 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowlist(self) -> set[str]:
        return {item.strip() for item in self.allowed_sender_ids.split(",") if item.strip()}


settings = Settings()
