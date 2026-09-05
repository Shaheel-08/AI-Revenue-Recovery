"""RecoverOS core configuration."""
from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os
from pathlib import Path


# Resolve project root (two levels up from this file → backend/)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_PROJECT_DIR = _BACKEND_DIR.parent


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{(_PROJECT_DIR / 'data' / 'recoveros.db').as_posix()}",
        description="Async SQLAlchemy database URL",
    )

    # ── Razorpay ──────────────────────────────────────────────────────
    razorpay_key_id: str = Field(default="rzp_test_mock", description="Razorpay key ID")
    razorpay_key_secret: str = Field(default="mock_secret", description="Razorpay key secret")
    razorpay_mock_mode: bool = Field(default=True, description="Use mock Razorpay client")

    # ── Server ────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # ── Guardrail Defaults ────────────────────────────────────────────
    max_retries: int = Field(default=3, description="Max auto-retry attempts per transaction")
    max_discount_percent: float = Field(default=15.0, description="Maximum discount percentage")
    max_touchpoints_72h: int = Field(default=5, description="Circuit-breaker: max contact in 72h window")
    quiet_hour_start: int = Field(default=22, description="No-contact window start (24h clock)")
    quiet_hour_end: int = Field(default=8, description="No-contact window end (24h clock)")
    approval_threshold_amount: float = Field(
        default=50000.0,
        description="Transactions above this amount require human approval",
    )

    # ── Synthetic Data ────────────────────────────────────────────────
    synthetic_data_seed: int = 42
    synthetic_data_count: int = 2000

    # ── Paths ─────────────────────────────────────────────────────────
    data_dir: str = Field(
        default=(_PROJECT_DIR / "data").as_posix(),
        description="Directory for data artifacts",
    )

    model_config = {"env_file": str(_PROJECT_DIR / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return cached settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
