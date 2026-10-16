from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env.fastapi', extra='ignore', hide_input_in_errors=True)
    database_url: str = 'postgresql+psycopg://localhost:5433/fitgate'
    secret_key: str = Field(min_length=48)
    environment: str = 'development'
    allowed_origins: str = 'http://127.0.0.1:5174,http://localhost:5174,http://127.0.0.1:8001,http://localhost:8001'
    demo_mode: bool = False
    local_sample_data: bool = False
    allow_device_simulation: bool = False
    allow_single_sensor_prototype: bool = False
    single_sensor_prototype_device_code: str = ''
    db_lock_timeout_ms: int = Field(default=3000,ge=100,le=30000)
    db_statement_timeout_ms: int = Field(default=15000,ge=1000,le=120000)
    db_idle_transaction_timeout_ms: int = Field(default=30000,ge=1000,le=120000)
    access_minutes: int = 15
    refresh_hours: int = 8

    @model_validator(mode='after')
    def local_accounts_require_development(self):
        if self.local_sample_data and self.environment != 'development':
            raise ValueError('Public sample accounts require a local development installation')
        if self.local_sample_data:
            from sqlalchemy.engine import make_url
            url = make_url(self.database_url)
            if (url.get_backend_name() != 'postgresql' or url.host != '127.0.0.1'
                    or url.port != 5433 or url.database != 'fitgate_local'
                    or url.username != 'fitgate' or url.query):
                raise ValueError('Local sample accounts require the isolated local installation target')
        return self

    @property
    def ALLOW_DEVICE_SIMULATION(self):
        return self.allow_device_simulation


@lru_cache
def get_settings():
    return Settings()

settings = get_settings()
