"""Authentication data models.

Token data transfer objects for login, refresh, and me responses.
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class TokenPair:
    """Represents an access token + refresh token pair."""

    access_token: str
    refresh_token: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": "Bearer",
        }


@dataclass
class AuthResponse:
    """Standard authentication response with tokens + user info."""

    tokens: TokenPair
    user: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.tokens.to_dict(),
            "user": self.user,
        }


@dataclass
class RefreshResponse:
    """Refresh token response."""

    access_token: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "access_token": self.access_token,
            "token_type": "Bearer",
        }
