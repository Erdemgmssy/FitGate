from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env.fastapi', extra='ignore', hide_input_in_errors=True)
    database_url: str = 'postgresql+psycopg://localhost:5433/fitgate'
    secret_key: str = Field(min_length=48)
    environment: str = 'development'
    allowed_origins: str = 'http://127.0.0.1:5174,http://localhost:5174,http://127.0.0.1:8001,http://localhost:8001'
    demo_mode: bool = False
    allow_device_simulation: bool = False
    allow_single_sensor_prototype: bool = False
    single_sensor_prototype_device_code: str = ''
    db_lock_timeout_ms: int = Field(default=3000,ge=100,le=30000)
    db_statement_timeout_ms: int = Field(default=15000,ge=1000,le=120000)
    db_idle_transaction_timeout_ms: int = Field(default=30000,ge=1000,le=120000)
    access_minutes: int = 15
    refresh_hours: int = 8

    @property
    def ALLOW_DEVICE_SIMULATION(self):
        return self.allow_device_simulation


@lru_cache
def get_settings():
    return Settings()

settings = get_settings()
