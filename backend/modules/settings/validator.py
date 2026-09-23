"""Validator for application settings input."""

import json
from typing import Any, Dict

from backend.modules.settings.model import ApplicationSetting


class SettingsValidator:
    """Validates incoming setting values before persistence."""

    SUPPORTED_LANGUAGES = ("en", "ar", "fr", "de", "es")
    SUPPORTED_THEMES = ("light", "dark")
    SUPPORTED_DATE_FORMATS = ("YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MM-YYYY")
    SUPPORTED_NUMBER_FORMATS = ("#,##0.00", "#,##0", "0,00", "0.00")
    MIN_PAGINATION = 5
    MAX_PAGINATION = 200

    @classmethod
    def validate_setting(cls, key: str, value: Any, value_type: str = "string") -> ApplicationSetting:
        """Validate and return an ApplicationSetting for a single key/value pair."""
        if value_type not in ApplicationSetting.VALID_TYPES:
            raise ValueError(f"Invalid value_type. Must be one of: {', '.join(ApplicationSetting.VALID_TYPES)}")

        str_value = cls._coerce_to_string(key, value, value_type)
        return ApplicationSetting(setting_key=key, setting_value=str_value, value_type=value_type)

    @classmethod
    def _coerce_to_string(cls, key: str, value: Any, value_type: str) -> str:
        if value is None:
            return None

        if value_type == "integer":
            n = int(value)
            if key == "pagination_size" and not (cls.MIN_PAGINATION <= n <= cls.MAX_PAGINATION):
                raise ValueError(f"Pagination size must be between {cls.MIN_PAGINATION} and {cls.MAX_PAGINATION}")
            return str(n)

        if value_type == "boolean":
            return str(bool(value)).lower()

        if value_type == "json":
            if isinstance(value, str):
                json.loads(value)  # validate it parses
                return value
            return json.dumps(value)

        # string
        s = str(value).strip()
        if key == "default_language" and s not in cls.SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language. Must be one of: {', '.join(cls.SUPPORTED_LANGUAGES)}")
        if key == "default_theme" and s not in cls.SUPPORTED_THEMES:
            raise ValueError(f"Unsupported theme. Must be one of: {', '.join(cls.SUPPORTED_THEMES)}")
        if key == "date_format" and s not in cls.SUPPORTED_DATE_FORMATS:
            raise ValueError(f"Unsupported date format. Must be one of: {', '.join(cls.SUPPORTED_DATE_FORMATS)}")
        if key == "number_format" and s not in cls.SUPPORTED_NUMBER_FORMATS:
            raise ValueError(f"Unsupported number format. Must be one of: {', '.join(cls.SUPPORTED_NUMBER_FORMATS)}")
        return s

    @classmethod
    def validate_application_settings_update(cls, data: Dict[str, Any]) -> Dict[str, ApplicationSetting]:
        """Validate a bulk application settings update payload."""
        if not data:
            raise ValueError("No settings provided")

        validated = {}
        for key, value in data.items():
            if not key or not isinstance(key, str):
                raise ValueError("Setting key must be a non-empty string")
            vt = "string"
            if isinstance(value, dict):
                vt = value.get("value_type", "string")
                value = value.get("value")
            elif isinstance(value, bool):
                vt = "boolean"
            elif isinstance(value, int):
                vt = "integer"
            validated[key] = cls.validate_setting(key, value, vt)
        return validated

    @classmethod
    def validate_user_preferences(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user preference fields (language, theme, date_format, etc.)."""
        if not data:
            raise ValueError("No preference data provided")

        allowed = {"language", "theme", "date_format", "number_format", "timezone", "pagination_size"}
        validated = {}
        for k, v in data.items():
            if k not in allowed:
                continue
            if k == "language" and v not in cls.SUPPORTED_LANGUAGES:
                raise ValueError(f"Unsupported language. Must be one of: {', '.join(cls.SUPPORTED_LANGUAGES)}")
            if k == "theme" and v not in cls.SUPPORTED_THEMES:
                raise ValueError(f"Unsupported theme. Must be one of: {', '.join(cls.SUPPORTED_THEMES)}")
            if k == "date_format" and v not in cls.SUPPORTED_DATE_FORMATS:
                raise ValueError(f"Unsupported date format. Must be one of: {', '.join(cls.SUPPORTED_DATE_FORMATS)}")
            if k == "number_format" and v not in cls.SUPPORTED_NUMBER_FORMATS:
                raise ValueError(f"Unsupported number format. Must be one of: {', '.join(cls.SUPPORTED_NUMBER_FORMATS)}")
            if k == "pagination_size":
                n = int(v)
                if not (cls.MIN_PAGINATION <= n <= cls.MAX_PAGINATION):
                    raise ValueError(f"Pagination size must be between {cls.MIN_PAGINATION} and {cls.MAX_PAGINATION}")
                v = n
            if k == "timezone" and not isinstance(v, str):
                raise ValueError("Timezone must be a string")
            validated[k] = v
        return validated

    @classmethod
    def validate_company_settings(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate company settings update payload."""
        if not data:
            raise ValueError("No company data provided")

        allowed = {"name", "tax_registration_number", "email", "phone", "address", "website",
                    "default_currency", "default_tax_rate", "fiscal_year_start"}
        validated = {}
        for k, v in data.items():
            if k not in allowed:
                continue
            if k == "name":
                if not v or not str(v).strip():
                    raise ValueError("Company name is required")
                validated[k] = str(v).strip()
            elif k == "email":
                if v and not _is_valid_email(str(v)):
                    raise ValueError("Invalid email format")
                validated[k] = str(v).strip() if v else None
            elif k == "default_tax_rate":
                validated[k] = float(v)
            elif k == "default_currency":
                s = str(v).strip().upper()
                if len(s) != 3:
                    raise ValueError("Currency must be a 3-letter code")
                validated[k] = s
            elif k == "fiscal_year_start":
                import re
                if not re.match(r"^\d{2}-\d{2}$", str(v)):
                    raise ValueError("Fiscal year start must be in MM-DD format")
                validated[k] = str(v)
            else:
                validated[k] = str(v).strip() if v else None
        return validated


def _is_valid_email(email: str) -> bool:
    import re
    return bool(re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email))
