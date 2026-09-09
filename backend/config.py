"""Application configuration loaded from environment variables."""

import logging
import os
import secrets

from dotenv import load_dotenv

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cwd = os.getcwd()

logger = logging.getLogger(__name__)

_DEFAULT_CSP_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self'"
)


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable.

    Accepted truthy values: 1, true, yes, on (case-insensitive).
    Anything else falls back to the provided default.

    Args:
        name: Environment variable name.
        default: Value returned when the variable is absent.

    Returns:
        Parsed boolean value.
    """
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_env_file() -> None:
    """Load the .env file from the standard search paths, if present.

    The ``ENV_FILE`` override is honoured first, followed by the
    current working directory and the project root.
    """
    candidates = []
    env_file = os.environ.get("ENV_FILE")
    if env_file:
        candidates.append(env_file)
    candidates.extend([
        os.path.join(_cwd, '.env'),
        os.path.join(_project_root, '.env'),
        os.path.normpath(os.path.join(_project_root, '..', '.env')),
    ])
    for path in candidates:
        if path and os.path.isfile(path):
            load_dotenv(path, override=False)
            return
    load_dotenv()


_load_env_file()


class BaseConfig:
    """Base configuration shared across all environments.

    Reads all settings from environment variables. Refuses to start
    if critical secrets are missing.
    """

    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_NAME = os.environ.get("DB_NAME", "invoice_system")
    DB_USER = os.environ.get("DB_USER", "invoice_app")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_POOL_NAME = os.environ.get("DB_POOL_NAME", "invoice_pool")
    DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))

    JWT_ACCESS_TOKEN_EXPIRES = 3600
    JWT_REFRESH_TOKEN_EXPIRES = 2592000  # 30 days
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(_project_root, "backend", "uploads"),
    )

    SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.environ.get("SERVER_PORT", "5001"))
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")

    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    ).split(",")
    CORS_EXPAND_LAN = _env_bool("CORS_EXPAND_LAN", True)

    SECURITY_HEADERS_ENABLED = _env_bool("SECURITY_HEADERS_ENABLED", True)
    CSP_ENABLED = _env_bool("CSP_ENABLED", False)
    CSP_POLICY = os.environ.get("CSP_POLICY", _DEFAULT_CSP_POLICY)
    HSTS_ENABLED = _env_bool("HSTS_ENABLED", False)

    RATE_LIMIT_ENABLED = _env_bool("RATE_LIMIT_ENABLED", True)

    ALLOW_DEV_SECRET_FALLBACK = False

    FRONTEND_DIST = os.environ.get(
        "FRONTEND_DIST",
        os.path.join(_project_root, "frontend", "dist"),
    )
    SERVE_STATIC = False
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls) -> None:
        """Validate that all required secrets are configured.

        In development, missing secrets are replaced with freshly generated
        random values so the app can start without a .env file. In every
        other environment, missing secrets abort startup.

        Raises:
            ValueError: If SECRET_KEY or JWT_SECRET_KEY is missing in a
                non-development environment.
        """
        missing = []
        if not cls.SECRET_KEY:
            missing.append("SECRET_KEY")
        if not cls.JWT_SECRET_KEY:
            missing.append("JWT_SECRET_KEY")
        if not missing:
            return
        if not getattr(cls, "ALLOW_DEV_SECRET_FALLBACK", False):
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Set them in your .env file or environment before starting the application."
            )
        for name in missing:
            generated = secrets.token_urlsafe(48)
            setattr(cls, name, generated)
            logger.warning(
                "%s is not set; generated a random development secret. "
                "Set it explicitly for reproducible sessions.",
                name,
            )


class DevelopmentConfig(BaseConfig):
    """Development configuration.

    Allows the app to boot without SECRET_KEY / JWT_SECRET_KEY by
    generating random values. CSP and HSTS stay off so the Vite dev
    server (HMR over websocket) and plain-HTTP local testing keep
    working unchanged.
    """

    DEBUG = True
    ALLOW_DEV_SECRET_FALLBACK = True


class ProductionConfig(BaseConfig):
    """Production configuration.

    Requires explicit secrets. Serves the built SPA and keeps CSP enabled
    by default; HSTS is opt-in and should only be enabled behind HTTPS.
    """

    DEBUG = False
    SERVE_STATIC = True
    CSP_ENABLED = _env_bool("CSP_ENABLED", True)


def get_config() -> BaseConfig:
    """Select configuration class based on FLASK_ENV.

    Returns:
        Configuration class instance.
    """
    env = os.environ.get("FLASK_ENV", "development")
    if env == "production":
        return ProductionConfig
    return DevelopmentConfig


Config = BaseConfig
