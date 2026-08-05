from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EM_", env_file=".env", extra="ignore")

    mode: str = "edge"
    environment: str = "development"
    release: str = "0.9.0"
    secret_key: str = "development-only-secret-key-change-me"
    edge_database_url: str = "sqlite:///./data/edge.db"
    control_database_url: str = "sqlite:///./data/control-room.db"
    control_room_url: str = "http://localhost:8001"
    edge_id: str = "00000000-0000-4000-8000-000000000001"
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    demo_admin_password: str = "EnergyDemo!2026"
    edge_token: str = "demo-edge-token-change-me"
    tailscale_provider: str = "fake"
    tailscale_oauth_client_id: str = ""
    tailscale_oauth_client_secret: str = ""
    tailscale_tailnet: str = ""
    webhook_secret: str = "change-me-webhook"
    simulator_host: str = "127.0.0.1"
    polling_enabled: bool = True
    sync_enabled: bool = True
    seed_demo: bool = True
    telemetry_retention_days: int = 730
    control_raw_retention_days: int = 30
    rollup_retention_days: int = 3650
    sent_outbox_retention_days: int = 30
    maintenance_interval_seconds: int = 3600
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    backup_retention_count: int = 14
    backup_directory: str = "./data/backups"
    network_management_enabled: bool = False

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"edge", "control-room"}:
            raise ValueError("mode must be edge or control-room")
        return value

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError("environment must be development, test or production")
        return value

    @field_validator("telemetry_retention_days")
    @classmethod
    def validate_retention(cls, value: int) -> int:
        if value < 30:
            raise ValueError("telemetry retention must be at least 30 days")
        return value

    @field_validator("control_raw_retention_days")
    @classmethod
    def validate_control_retention(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Control Room raw telemetry retention must be at least one day")
        return value

    @field_validator("rollup_retention_days")
    @classmethod
    def validate_rollup_retention(cls, value: int) -> int:
        if value < 30:
            raise ValueError("rollup retention must be at least 30 days")
        return value

    @field_validator("edge_id")
    @classmethod
    def validate_edge_id(cls, value: str) -> str:
        import uuid
        return str(uuid.UUID(value))

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.environment != "production":
            return self
        values = {
            "EM_SECRET_KEY": self.secret_key,
            "EM_EDGE_TOKEN": self.edge_token,
            "EM_WEBHOOK_SECRET": self.webhook_secret,
            "EM_BOOTSTRAP_ADMIN_PASSWORD": self.demo_admin_password,
        }
        markers = ("change-me", "development-only", "demo-", "generare_", "impostare_")
        invalid = [name for name, value in values.items() if len(value) < 24 or len(set(value)) < 10 or any(marker in value.lower() for marker in markers)]
        if len(set(values.values())) != len(values):
            invalid.append("secrets_must_be_distinct")
        if self.seed_demo:
            invalid.append("EM_SEED_DEMO")
        if self.mode == "edge" and self.sync_enabled and self.edge_id == "00000000-0000-4000-8000-000000000001":
            invalid.append("EM_EDGE_ID")
        if invalid:
            raise ValueError(f"Unsafe production configuration: {', '.join(invalid)}")
        return self

    @property
    def database_url(self) -> str:
        return self.edge_database_url if self.mode == "edge" else self.control_database_url

    @property
    def cors_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def ensure_sqlite_directory(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            Path(self.database_url.removeprefix("sqlite:///" )).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
