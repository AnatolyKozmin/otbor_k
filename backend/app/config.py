from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    DATABASE_URL: str = "sqlite:///./koord_hr.db"
    SPREADSHEET_ID: str = ""
    GOOGLE_CREDENTIALS_PATH: str = "credentials.json"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    model_config = {"env_file": ".env"}


settings = Settings()
