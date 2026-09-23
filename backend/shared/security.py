"""Shared security helpers for password hashing and JWT issuance.

Centralizes the bcrypt password routines and the JWT access-token
claims used across services so every module uses the same logic.
"""

from typing import Any

import bcrypt
from flask_jwt_extended import create_access_token


MIN_PASSWORD_LENGTH = 8
"""Minimum length enforced for newly set passwords across the platform."""


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        password: The plaintext password.

    Returns:
        The bcrypt hash string.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        password: The plaintext password.
        password_hash: The stored bcrypt hash.

    Returns:
        True when the password matches the hash, False otherwise.
    """
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token_for_user(user: Any) -> str:
    """Issue a JWT access token carrying the user's identity and claims.

    Args:
        user: A user object exposing id, email, role, full_name and
            company_id.

    Returns:
        The signed JWT access token string.
    """
    return create_access_token(
        identity=str(user.id),
        additional_claims={
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name,
            "company_id": getattr(user, "company_id", None),
        },
    )
