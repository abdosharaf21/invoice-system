"""Application setting model for the key/value settings store."""

from datetime import datetime
from typing import Optional


class ApplicationSetting:
    """A single application-level setting stored as a key/value pair.

    Attributes:
        id: Unique identifier.
        setting_key: Unique key (e.g. 'application_name').
        setting_value: The value (stored as text; typed on read).
        value_type: One of 'string', 'integer', 'boolean', 'json'.
        description: Human-readable description.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
    """

    VALID_TYPES = ("string", "integer", "boolean", "json")

    def __init__(
        self,
        id: Optional[int] = None,
        setting_key: Optional[str] = None,
        setting_value: Optional[str] = None,
        value_type: str = "string",
        description: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> None:
        self.id = id
        self.setting_key = setting_key
        self.setting_value = setting_value
        self.value_type = value_type
        self.description = description
        self.created_at = created_at
        self.updated_at = updated_at

    def typed_value(self):
        """Return the value cast to its declared type."""
        if self.setting_value is None:
            return None
        if self.value_type == "integer":
            return int(self.setting_value)
        if self.value_type == "boolean":
            return self.setting_value.lower() in ("1", "true", "yes")
        if self.value_type == "json":
            import json
            return json.loads(self.setting_value)
        return self.setting_value

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "setting_key": self.setting_key,
            "setting_value": self.setting_value,
            "value_type": self.value_type,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __str__(self) -> str:
        return f"ApplicationSetting(key={self.setting_key}, value={self.setting_value})"

    def __repr__(self) -> str:
        return self.__str__()
