"""Authentication service.

Contains all authentication business logic: login, logout, token refresh,
and current user retrieval. Delegates DB operations to the repository.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Set

from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

from backend.middleware.exceptions import (
    UnauthorizedException,
    NotFoundException,
)
from backend.modules.auth.model import AuthResponse, RefreshResponse, TokenPair
from backend.modules.auth.repository import AuthRepository
from backend.modules.auth.validator import auth_validator
from backend.modules.users.repository import UserRepository
from backend.shared.security import (
    MIN_PASSWORD_LENGTH,
    create_access_token_for_user,
    hash_password,
    verify_password,
)


class AuthService:
    """Handles authentication business logic."""

    def __init__(
        self,
        auth_repository: AuthRepository,
        user_repository: UserRepository,
        blocklist: Set[str] = None,
    ) -> None:
        self._auth_repository = auth_repository
        self._user_repository = user_repository
        self._blocklist = blocklist if blocklist is not None else set()

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate a user and return tokens.

        Raises:
            UnauthorizedException: If credentials are invalid.
            ValueError: If input is invalid.
        """
        auth_validator.validate_login(email, password)

        email = email.strip().lower()
        user = self._user_repository.get_by_email(email)

        if user is None:
            raise UnauthorizedException("Invalid email or password")

        if not verify_password(password, user.password_hash):
            raise UnauthorizedException("Invalid email or password")

        if not user.is_active:
            raise UnauthorizedException("Invalid email or password")

        access_token = create_access_token_for_user(user)
        refresh_token = create_refresh_token(identity=str(user.id))

        tokens = TokenPair(access_token=access_token, refresh_token=refresh_token)
        user_dict = user.to_dict()

        auth_response = AuthResponse(tokens=tokens, user=user_dict)
        return auth_response.to_dict()

    def logout(self, access_jti: str, refresh_jti: str) -> None:
        """Revoke both access and refresh tokens."""
        self._auth_repository.add_to_blocklist(
            access_jti, "access", datetime.now(timezone.utc)
        )
        self._auth_repository.add_to_blocklist(
            refresh_jti, "refresh", datetime.now(timezone.utc)
        )
        self._blocklist.add(access_jti)
        self._blocklist.add(refresh_jti)

    def refresh_tokens(self, refresh_token: str) -> Dict[str, str]:
        """Validate refresh token and issue a new access token.

        Raises:
            UnauthorizedException: If token is invalid or revoked.
            ValueError: If input is invalid.
        """
        auth_validator.validate_refresh_token(refresh_token)

        try:
            decoded = decode_token(refresh_token)
        except Exception:
            raise UnauthorizedException("Invalid or expired refresh token")

        jti = decoded.get("jti")
        token_type = decoded.get("type")

        if token_type != "refresh":
            raise UnauthorizedException("Token is not a refresh token")

        if self._auth_repository.is_blocklisted(jti):
            raise UnauthorizedException("Refresh token has been revoked")

        user_id = decoded.get("sub")
        user = self._user_repository.get_by_id(int(user_id)) if user_id else None
        if user is None:
            new_access_token = create_access_token(identity=user_id)
        else:
            new_access_token = create_access_token_for_user(user)

        return RefreshResponse(access_token=new_access_token).to_dict()

    def logout_refresh(self, refresh_token: str) -> None:
        """Revoke a refresh token."""
        auth_validator.validate_refresh_token(refresh_token)

        try:
            decoded = decode_token(refresh_token)
        except Exception:
            raise UnauthorizedException("Invalid refresh token")

        jti = decoded.get("jti")
        token_type = decoded.get("type")

        if token_type != "refresh":
            raise UnauthorizedException("Token is not a refresh token")

        exp_ts = decoded.get("exp")
        expiry = (
            datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            if exp_ts
            else datetime.now(timezone.utc)
        )

        self._auth_repository.add_to_blocklist(jti, "refresh", expiry)

    def get_current_user(self, user_id: str) -> Dict[str, Any]:
        """Retrieve current authenticated user profile.

        Raises:
            UnauthorizedException: If user not found or inactive.
            ValueError: If user_id is invalid.
        """
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            raise UnauthorizedException("Invalid token")

        user = self._user_repository.get_by_id(uid)

        if user is None:
            raise NotFoundException("User not found")

        return user.to_dict()

    def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> None:
        """Change a user's password.

        Raises:
            UnauthorizedException: If current password is incorrect.
            NotFoundException: If user not found.
            ValueError: If input is invalid.
        """
        if not current_password or not new_password:
            raise ValueError("current_password and new_password are required")
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"new_password must be at least {MIN_PASSWORD_LENGTH} characters"
            )

        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            raise UnauthorizedException("Invalid token")

        user = self._user_repository.get_by_id(uid)
        if user is None:
            raise NotFoundException("User not found")

        if not verify_password(current_password, user.password_hash):
            raise UnauthorizedException("Current password is incorrect")

        new_hash = hash_password(new_password)
        self._user_repository.update_password(uid, new_hash)
