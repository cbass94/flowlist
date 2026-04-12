# FlowList — pydantic-settings config
# TODO: load all .env variables into typed Settings dataclass
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_env: str = "development"
    app_base_url: str = "http://localhost"
    secret_key: str
    session_expire_hours: int = 168

    # Timezone
    tz: str = "America/Chicago"

    # Database (assembled by docker-compose or set manually)
    database_url: str

    # Redis
    redis_url: str

    # Google OAuth — work
    google_work_client_id: str
    google_work_client_secret: str
    google_work_redirect_uri: str

    # Google OAuth — personal
    google_personal_client_id: str
    google_personal_client_secret: str
    google_personal_redirect_uri: str

    # Google Calendar IDs
    work_calendar_id: str
    personal_calendar_id: str

    # Anthropic
    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Scheduling rules
    schedule_work_start_hour: int = 8
    schedule_work_end_hour: int = 17
    schedule_hard_start_hour: int = 7
    schedule_hard_end_hour: int = 22
    schedule_buffer_minutes: int = 30
    schedule_max_block_minutes: int = 120
    schedule_min_block_minutes: int = 60

    # Watchdog
    watchdog_threshold_days: int = 14
    watchdog_cron: str = "0 8 * * *"

    # CORS
    allowed_origins: str = "http://localhost"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()  # type: ignore[call-arg]
