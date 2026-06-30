from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_db: str = "exl_financial_intelligence"
    postgres_user: str = "exl"
    postgres_password: str = "exl_password"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    log_level: str = "INFO"
    raw_data_dir: str = "data/raw/EXL"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
