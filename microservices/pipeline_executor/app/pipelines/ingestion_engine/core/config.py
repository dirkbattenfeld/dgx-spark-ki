# pipeline_executor/app/pipelines/ingestion_engine/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL für Ingestion
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_port: int
    postgres_url: str

    # Ingestion Engine Tuning
    ingestion_worker_concurrency: int = 4
    ingestion_batch_size: int = 5   # 500 für Produktion

    # Pydantic v2 Konfiguration
    model_config = SettingsConfigDict(
        env_file=".env",          # Sucht lokal nach einer .env (falls ohne Docker gestartet)
        env_file_encoding="utf-8",
        extra="ignore"            # Ignoriert andere Variablen in der .env, die hier nicht definiert sind
    )

settings = Settings()
