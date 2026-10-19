from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    PROJECT_NAME: str = "Clara Rosa Webstore API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:4200",
        "http://localhost:4201",
        "http://localhost:4202",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                return json.loads(v)
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    MONGODB_URL: str = "mongodb://127.0.0.1:27017"
    MONGODB_DB_NAME: str = "clara_rosa_store"

    JWT_SECRET_KEY: str = "clara-rosa-dev-secret-key-change-in-production-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:4201"
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 60
    RATE_LIMIT_ENABLED: bool = True

    # EMAIL_BACKEND: "console" (development only, logs the message) or "smtp"
    EMAIL_BACKEND: str = "console"
    EMAIL_FROM: str = "Printoy 3D <no-reply@printoy.pt>"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True

    BOOTSTRAP_ADMIN_ENABLED: bool = True
    ADMIN_INITIAL_EMAIL: str = "admin@clararosa.pt"
    ADMIN_INITIAL_PASSWORD: str = "admin"
    ADMIN_INITIAL_NAME: str = "Clara Rosa Admin"


settings = Settings()
