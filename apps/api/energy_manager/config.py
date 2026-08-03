from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EM_", env_file=".env", extra="ignore")

    mode: str = "edge"
    secret_key: str = "development-only-secret-key-change-me"
    edge_database_url: str = "sqlite:///./data/edge.db"
    control_database_url: str = "sqlite:///./data/control-room.db"
    control_room_url: str = "http://localhost:8001"
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

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"edge", "control-room"}:
            raise ValueError("mode must be edge or control-room")
        return value

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
