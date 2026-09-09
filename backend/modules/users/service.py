"""User service for user-related business logic."""

from typing import List, Optional, Set

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

    DEFAULT_ROLE = "viewer"

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

        if not user.is_active:
            raise ValueError("Account is inactive")

        self._user_repository.update_last_login(user.id)

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

        if self._user_repository.exists_by_username(validated["username"]):
            raise ValueError("Username already exists")

        if self._user_repository.exists_by_email(validated["email"]):
            raise ValueError("Email already exists")

        password_hash = hash_password(validated["password"])
        roles = validated["roles"] or [self.DEFAULT_ROLE]

        user = User(
            company_id=validated["company_id"],
            username=validated["username"],
            email=validated["email"],
            password_hash=password_hash,
            first_name=validated["first_name"],
            last_name=validated["last_name"],
            is_active=validated["status"] == "active",
            roles=roles,
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

        if "username" in validated and validated["username"] != user.username:
            if self._user_repository.exists_by_username(validated["username"]):
                raise ValueError("Username already exists")

        next_role = validated.get("roles", [user.role])[0] if validated.get("roles", [user.role]) else user.role
        self._guard_last_active_admin(
            user,
            next_role=next_role,
            next_status=validated.get("status", user.status),
        )

        if "username" in validated:
            user.username = validated["username"]
        if "email" in validated:
            user.email = validated["email"]
        if "first_name" in validated:
            user.first_name = validated["first_name"]
        if "last_name" in validated:
            user.last_name = validated["last_name"]
        if "company_id" in validated:
            user.company_id = validated["company_id"]
        if "status" in validated:
            user.is_active = validated["status"] == "active"
        if "roles" in validated:
            if not validated["roles"]:
                raise ValueError("At least one role is required")
            self._user_repository.set_roles(user.id, validated["roles"])

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

        user.is_active = True
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

        user.is_active = False
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
        next_role: Optional[str],
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