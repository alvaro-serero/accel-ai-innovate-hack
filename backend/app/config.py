"""Reads settings from environment variables (and from .env when running locally)."""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    keenable_api_key: str = os.getenv("KEENABLE_API_KEY", "")
    n8n_webhook_url: str = os.getenv("N8N_WEBHOOK_URL", "")
    # Only one instance may poll the shared DB: off on laptops, on in production.
    enable_scheduler: bool = os.getenv("ENABLE_SCHEDULER", "false").lower() == "true"


settings = Settings()
