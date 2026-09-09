"""Authentication validators.

Input validation for authentication endpoints.
"""

import re
from typing import Optional


class AuthValidator:
    """Validates authentication request data."""

    EMAIL_REGEX = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )

    def validate_login(self, email: Optional[str], password: Optional[str]) -> None:
        """Validate login input.

        Raises:
            ValueError: If validation fails.
        """
        errors = []

        if not email or not email.strip():
            errors.append(("email", "Email is required"))
        elif not self.EMAIL_REGEX.match(email.strip()):
            errors.append(("email", "Invalid email format"))

        if not password:
            errors.append(("password", "Password is required"))
        elif len(password) < 6:
            errors.append(("password", "Password must be at least 6 characters"))

        if errors:
            error_msg = "; ".join(f"{f}: {m}" for f, m in errors)
            raise ValueError(error_msg)

    def validate_refresh_token(self, refresh_token: Optional[str]) -> None:
        """Validate refresh token input.

        Raises:
            ValueError: If validation fails.
        """
        if not refresh_token or not refresh_token.strip():
            raise ValueError("Refresh token is required")


auth_validator = AuthValidator()
