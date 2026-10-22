from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"


settings = Settings()