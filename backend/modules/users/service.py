"""User service for user-related business logic."""

from typing import Optional, List, Set

from backend.modules.users.model import User
from backend.modules.users.repository import UserRepository
from backend.modules.users.validator import UserValidator
from backend.shared.security import (
    create_access_token_for_user,
    hash_password,
    verify_password,
)


class UserService:
    """Service for user business operations.

    Handles all user-related business logic including authentication,
    registration, and user management.
    """

    def __init__(self, user_repository: UserRepository, blocklist: Set[str] = None) -> None:
        self._user_repository = user_repository
        self._blocklist = blocklist if blocklist is not None else set()

    def login(self, email: str, password: str) -> dict:
        """Authenticate a user by email and password.

        Raises:
            ValueError: If email or password is invalid.
            ValueError: If user account is inactive.
        """
        validated = UserValidator.validate_login({"email": email, "password": password})
        email = validated["email"]
        password = validated["password"]

        user = self._user_repository.get_by_email(email)
        if user is None:
            raise ValueError("Invalid email or password")

        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")

        if user.status != "active":
            raise ValueError("Account is inactive")

        access_token = create_access_token_for_user(user)

        return {
            "access_token": access_token,
            "user": user.to_dict()
        }

    def logout(self, jti: str) -> None:
        """Revoke a JWT token by adding it to the blocklist."""
        self._blocklist.add(jti)

    def get_user_by_id(self, user_id: int) -> User:
        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        return user

    def get_user_by_email(self, email: str) -> User:
        user = self._user_repository.get_by_email(email)
        if user is None:
            raise ValueError("User not found")
        return user

    def get_all_users(self) -> List[User]:
        return self._user_repository.get_all()

    def create_user(self, user_data: dict) -> User:
        validated = UserValidator.validate_create_user(user_data)

        if self._user_repository.exists_by_email(validated["email"]):
            raise ValueError("Email already exists")

        password_hash = hash_password(validated["password"])

        user = User(
            full_name=validated["full_name"],
            email=validated["email"],
            password_hash=password_hash,
            phone=validated["phone"],
            role=validated["role"],
            status=validated["status"]
        )

        return self._user_repository.create(user)

    def update_user(self, user_id: int, data: dict) -> User:
        validated = UserValidator.validate_update_user(data)

        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        if "email" in validated and validated["email"] != user.email:
            if self._user_repository.exists_by_email(validated["email"]):
                raise ValueError("Email already exists")

        self._guard_last_active_admin(
            user,
            next_role=validated.get("role", user.role),
            next_status=validated.get("status", user.status),
        )

        if "full_name" in validated:
            user.full_name = validated["full_name"]
        if "email" in validated:
            user.email = validated["email"]
        if "phone" in validated:
            user.phone = validated["phone"]
        if "role" in validated:
            user.role = validated["role"]
        if "status" in validated:
            user.status = validated["status"]

        updated = self._user_repository.update(user)
        if updated is None:
            raise ValueError("Failed to update user")

        return updated

    def change_password(self, user_id: int, new_password: str) -> User:
        validated = UserValidator.validate_change_password({"new_password": new_password})
        new_password = validated["new_password"]

        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        user.password_hash = hash_password(new_password)

        updated = self._user_repository.update(user)
        if updated is None:
            raise ValueError("Failed to update password")

        return updated

    def activate_user(self, user_id: int) -> User:
        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        user.status = "active"
        updated = self._user_repository.update(user)
        if updated is None:
            raise ValueError("Failed to activate user")

        return updated

    def deactivate_user(self, user_id: int) -> User:
        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        self._guard_last_active_admin(
            user,
            next_role=user.role,
            next_status="inactive",
        )

        user.status = "inactive"
        updated = self._user_repository.update(user)
        if updated is None:
            raise ValueError("Failed to deactivate user")

        return updated

    def delete_user(self, user_id: int) -> bool:
        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        self._guard_last_active_admin(
            user,
            next_role=user.role,
            next_status=user.status,
            removing=True,
        )

        deleted = self._user_repository.delete(user_id)
        if not deleted:
            raise ValueError("User not found")

        return True

    def _guard_last_active_admin(
        self,
        user: User,
        next_role: str,
        next_status: str,
        removing: bool = False,
    ) -> None:
        """Prevent removing, demoting, or deactivating the last active admin."""
        is_active_admin = user.role == "admin" and user.status == "active"
        if not is_active_admin:
            return

        if removing or next_role != "admin" or next_status != "active":
            active_admins = self._user_repository.count_active_admins()
            if active_admins <= 1:
                raise ValueError(
                    "Cannot remove, demote, or deactivate the last active admin"
                )
