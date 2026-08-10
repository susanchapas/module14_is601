# app/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database settings (keeping your existing default)
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/fastapi_db"

    # Separate database for the test suite, which drops and recreates every
    # table on each run. It must never be the same as DATABASE_URL, or running
    # the tests would destroy the application's data. Created by init-db.sh when
    # the postgres volume is first initialized.
    TEST_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/fastapi_test_db"

    # JWT Settings
    #
    # Deliberately no defaults: a missing value must fail loudly at startup
    # rather than yield a working app signed with a public, well-known key.
    # See .env.example for how to supply them.
    JWT_SECRET_KEY: str
    JWT_REFRESH_SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Security
    BCRYPT_ROUNDS: int = 12

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

@lru_cache()
def get_settings() -> Settings:
    """Return the one Settings instance the whole application reads from."""
    return Settings()