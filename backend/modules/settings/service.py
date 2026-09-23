"""Service layer for application settings business logic."""

from typing import Dict

from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.service import record_event
from backend.modules.settings.model import ApplicationSetting
from backend.modules.settings.repository import ApplicationSettingRepository
from backend.modules.settings.validator import SettingsValidator


class ApplicationSettingService:
    """Manages application-wide settings (read/write)."""

    def __init__(self, repository: ApplicationSettingRepository) -> None:
        self._repository = repository

    def get_all_settings(self) -> Dict[str, object]:
        """Return all settings as a flat {key: typed_value} dict."""
        return self._repository.get_all_as_dict()

    def get_setting(self, key: str) -> ApplicationSetting:
        """Fetch a single setting by key. Raises ValueError if not found."""
        s = self._repository.get_by_key(key)
        if s is None:
            raise ValueError(f"Setting '{key}' not found")
        return s

    def update_settings(self, data: Dict) -> Dict[str, object]:
        """Validate and persist one or more application settings."""
        validated = SettingsValidator.validate_application_settings_update(data)
        valid_values = {s.setting_key: s.setting_value for s in validated.values()}
        before = self.get_all_settings()
        self._repository.upsert_many(list(validated.values()))
        after = self.get_all_settings()
        record_event(
            action=AuditLog.ACTION_UPDATE,
            resource_type="setting",
            result=AuditLog.RESULT_SUCCESS,
            before_state=_redacted_changes(before, valid_values, "before"),
            after_state=_redacted_changes(after, valid_values, "after"),
        )
        return after

    def get_settings_for_frontend(self) -> Dict[str, object]:
        """Return only the settings the frontend needs (safe subset)."""
        all_settings = self.get_all_settings()
        frontend_keys = {
            "application_name", "application_subtitle", "default_language",
            "default_theme", "date_format", "number_format", "timezone",
            "pagination_size",
        }
        return {k: v for k, v in all_settings.items() if k in frontend_keys}


_SENSITIVE_SETTING_TERMS = ("password", "secret", "token", "api_key", "smtp")


def _redacted_changes(settings: Dict[str, object], changed_keys: Dict[str, str], side: str) -> Dict[str, object]:
    """Return a compact {key: value} map of only the changed settings.

    Keys that look sensitive (password/secret/token) are never mirrored into
    the audit record; they are replaced by a redaction marker.
    """
    result: Dict[str, object] = {}
    for key in changed_keys:
        lowered = key.lower()
        if any(term in lowered for term in _SENSITIVE_SETTING_TERMS):
            result[key] = "[redacted]"
            continue
        result[key] = settings.get(key)
    return result
