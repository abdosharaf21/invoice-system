"""Unit tests for application configuration (Phase 14 gap G6).

Exercises the environment parsing, environment selection, production
defaults and startup secret validation. All tests are pure and offline;
they deliberately avoid mutating the real config classes (secrets are
tested via throwaway subclasses).
"""

import pytest

from backend import config as config_module
from backend.config import (
    BaseConfig,
    DevelopmentConfig,
    ProductionConfig,
    _env_bool,
    get_config,
)


class TestEnvBool:
    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "True", "yes", "on", " 1 "])
    def test_truthy_values(self, monkeypatch, raw):
        monkeypatch.setenv("TEST_BOOL", raw)
        assert _env_bool("TEST_BOOL", False) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off", "anything", ""])
    def test_present_non_truthy_values_resolve_false(self, monkeypatch, raw):
        # An explicitly present but unrecognised value is treated as OFF,
        # regardless of the requested default.
        monkeypatch.setenv("TEST_BOOL", raw)
        assert _env_bool("TEST_BOOL", True) is False

    def test_missing_variable_uses_default(self, monkeypatch):
        monkeypatch.delenv("TEST_BOOL", raising=False)
        assert _env_bool("TEST_BOOL", True) is True
        assert _env_bool("TEST_BOOL", False) is False


class TestGetConfig:
    def test_default_env_selects_development(self, monkeypatch):
        monkeypatch.setenv("FLASK_ENV", "development")
        assert get_config() is DevelopmentConfig

    @pytest.mark.parametrize("env", ["production"])
    def test_production_env_selects_production(self, monkeypatch, env):
        monkeypatch.setenv("FLASK_ENV", env)
        assert get_config() is ProductionConfig

    def test_unknown_env_falls_back_to_development(self, monkeypatch):
        monkeypatch.delenv("FLASK_ENV", raising=False)
        assert get_config() is DevelopmentConfig


class TestConfigDefaults:
    def test_static_base_constants(self):
        assert BaseConfig.JWT_TOKEN_LOCATION == ["headers"]
        assert BaseConfig.JWT_HEADER_NAME == "Authorization"
        assert BaseConfig.JWT_HEADER_TYPE == "Bearer"
        assert BaseConfig.MAX_CONTENT_LENGTH == 10 * 1024 * 1024
        assert BaseConfig.ALLOW_DEV_SECRET_FALLBACK is False
        assert BaseConfig.SERVE_STATIC is False
        assert BaseConfig.DB_PORT == 3306
        assert BaseConfig.JWT_ACCESS_TOKEN_EXPIRES == 3600
        assert BaseConfig.JWT_REFRESH_TOKEN_EXPIRES == 2592000

    def test_production_mode_defaults(self):
        # CORS LAN expansion off, CSP on, HSTS off, static serving on.
        assert ProductionConfig.DEBUG is False
        assert ProductionConfig.SERVE_STATIC is True
        assert ProductionConfig.CSP_ENABLED is True
        assert ProductionConfig.CORS_EXPAND_LAN is False
        assert ProductionConfig.RATE_LIMIT_EXEMPT_IPS == ""

    def test_development_mode_defaults(self):
        assert DevelopmentConfig.DEBUG is True
        assert DevelopmentConfig.ALLOW_DEV_SECRET_FALLBACK is True


class _ProdNoSecrets(ProductionConfig):
    SECRET_KEY = None
    JWT_SECRET_KEY = None
    ALLOW_DEV_SECRET_FALLBACK = False


class _ProdWithSecrets(ProductionConfig):
    SECRET_KEY = "s" * 40
    JWT_SECRET_KEY = "j" * 40
    ALLOW_DEV_SECRET_FALLBACK = False


class _DevNoSecrets(DevelopmentConfig):
    SECRET_KEY = None
    JWT_SECRET_KEY = None


class TestValidate:
    def test_validate_raises_when_secrets_missing_in_production(self):
        with pytest.raises(ValueError, match="SECRET_KEY, JWT_SECRET_KEY"):
            _ProdNoSecrets.validate()

    def test_validate_passes_when_secrets_present(self):
        _ProdWithSecrets.validate()  # must not raise

    def test_dev_fallback_generates_missing_secrets(self):
        _DevNoSecrets.validate()  # must not raise
        assert _DevNoSecrets.SECRET_KEY
        assert _DevNoSecrets.JWT_SECRET_KEY
        # The generated secrets must be printable (urlsafe, 48 bytes).
        assert len(_DevNoSecrets.SECRET_KEY) >= 32


class TestModuleConstants:
    def test_default_csp_policy_allows_self_only(self):
        policy = config_module._DEFAULT_CSP_POLICY
        assert "default-src 'self'" in policy
        assert "script-src 'self'" in policy
        assert "connect-src 'self'" in policy