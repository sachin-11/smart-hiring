from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Smart Hiring Platform"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/smart_hiring"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM Providers
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET: str = ""

    # SendGrid (report sharing)
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "reports@smart-hiring.example"

    # MLOps
    # mlflow>=3 puts the filesystem backend ("file:./mlruns") in maintenance mode by
    # default and refuses to write to it; sqlite is the modern default (also queryable
    # via mlflow.search_runs(), which the analytics dashboard needs).
    MLFLOW_TRACKING_URI: str = "sqlite:///mlflow.db"

    # Scheduled RAGAS + drift checks (replaces manual "Run" buttons on /analytics
    # with a recurring background job that also pushes Slack alerts on threshold
    # breach). Disabled by default in dev so local runs don't burn LLM tokens on
    # every backend restart.
    MLOPS_SCHEDULE_ENABLED: bool = False
    MLOPS_SCHEDULE_INTERVAL_HOURS: int = 24
    MLOPS_SCHEDULE_RAGAS_SAMPLE_SIZE: int = 5

    # Interview WS voice loop: how long to wait with no detected speech before
    # nudging the candidate, and before giving up entirely.
    INTERVIEW_WS_NUDGE_SECONDS: int = 20
    INTERVIEW_WS_TIMEOUT_SECONDS: int = 45
    INTERVIEW_WS_POLL_SECONDS: int = 5

    # Rate limiting (per client IP, backed by Redis so it's shared across workers).
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_REGISTER: str = "5/hour"
    RATE_LIMIT_FORGOT_PASSWORD: str = "3/hour"
    RATE_LIMIT_LLM_ENDPOINTS: str = "10/minute"

    # Auth
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_TTL_MINUTES: int = 30
    JWT_REFRESH_TOKEN_TTL_DAYS: int = 7

    # Notifications
    SLACK_WEBHOOK_URL: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Used to build links in outbound emails (e.g. the password reset link).
    FRONTEND_URL: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
