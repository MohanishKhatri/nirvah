import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


#: backend/ — so a relative sqlite path means the same file no matter where a script is run from
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _absolute_sqlite(url: str) -> str:
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return url
    path = url[len(prefix) :]
    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        return url
    return prefix + os.path.join(BASE_DIR, path.lstrip("./")).replace("\\", "/")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Plain settings object — everything comes from .env."""

    database_url: str = _absolute_sqlite(
        os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./nirvah.db")
    )

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    resend_api_key: str = os.getenv("RESEND_API_KEY", "")
    resend_from: str = os.getenv("RESEND_FROM", "NIRVAH <onboarding@resend.dev>")

    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "nirvah_admin_2024")
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    allowed_email_domain: str = os.getenv("ALLOWED_EMAIL_DOMAIN", "college.edu")
    reminder_after_hours: int = int(os.getenv("REMINDER_AFTER_HOURS", "24"))

    upload_dir: str = os.getenv("UPLOAD_DIR", "./uploads")

    #: When true the LLM layer returns deterministic fixtures instead of calling Gemini.
    use_llm_mock: bool = _bool("USE_LLM_MOCK", True)
    #: When true any bearer token is accepted and mapped to a demo student.
    dev_auth_bypass: bool = _bool("DEV_AUTH_BYPASS", True)

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
