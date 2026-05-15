from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required — startup fails with a clear Pydantic error if missing
    apple_health_webhook_secret: str
    clerk_secret_key: str
    clerk_issuer: str

    # Optional with defaults
    owner_email: str = ""
    frontend_origin: str = ""

    # Path settings — env-overridable for Docker/venv portability
    db_dir: Path = Path("/Volumes/NVME/health-dashboard/data")
    log_dir: Path = Path(__file__).parent / "logs"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
settings.log_dir.mkdir(parents=True, exist_ok=True)
