"""User service for user-related business logic."""

from datetime import datetime, timezone
from typing import List, Optional, Set

from backend.modules.auth.repository import AuthRepository
from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.service import build_snapshot, record_event
from backend.modules.companies.repository import CompanyRepository
from backend.modules.users.model import User
from backend.modules.users.repository import UserRepository
from backend.modules.users.validator import UserValidator
from backend.modules.settings.validator import SettingsValidator
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

    def __init__(
        self,
        user_repository: UserRepository,
        blocklist: Set[str] = None,
        company_repository: Optional[CompanyRepository] = None,
        auth_repository: Optional[AuthRepository] = None,
    ) -> None:
        self._user_repository = user_repository
        self._blocklist = blocklist if blocklist is not None else set()
        self._company_repository = company_repository
        self._auth_repository = auth_repository

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
            record_event(
                action=AuditLog.ACTION_LOGIN,
                resource_type="auth",
                result=AuditLog.RESULT_FAILURE,
                actor_email=email or None,
                metadata={"email": email or None},
            )
            raise ValueError("Invalid email or password")

        if not verify_password(password, user.password_hash):
            record_event(
                action=AuditLog.ACTION_LOGIN,
                resource_type="auth",
                resource_id=str(user.id),
                result=AuditLog.RESULT_FAILURE,
                actor_email=user.email,
                role=user.role,
                company_id=user.company_id,
                metadata={"email": user.email},
            )
            raise ValueError("Invalid email or password")

        if not user.is_active:
            record_event(
                action=AuditLog.ACTION_LOGIN,
                resource_type="auth",
                resource_id=str(user.id),
                result=AuditLog.RESULT_FAILURE,
                actor_email=user.email,
                role=user.role,
                company_id=user.company_id,
                metadata={"email": user.email},
            )
            raise ValueError("Account is inactive")

        self._user_repository.update_last_login(user.id)

        access_token = create_access_token_for_user(user)

        record_event(
            action=AuditLog.ACTION_LOGIN,
            resource_type="auth",
            resource_id=str(user.id),
            result=AuditLog.RESULT_SUCCESS,
            actor_id=user.id,
            actor_email=user.email,
            role=user.role,
            company_id=user.company_id,
            metadata={"email": user.email},
        )

        return {
            "access_token": access_token,
            "user": user.to_dict()
        }

    def logout(self, jti: str) -> None:
        """Revoke a JWT token by persisting it and adding it to the blocklist.

        When an auth repository is wired the JTI is persisted so the
        revocation survives an application restart and is visible to every
        worker process. The in-memory blocklist is updated in either case so
        the token is rejected immediately within the current process.
        """
        if self._auth_repository is not None:
            self._auth_repository.add_to_blocklist(
                jti, "access", datetime.now(timezone.utc)
            )
        self._blocklist.add(jti)
        record_event(
            action=AuditLog.ACTION_LOGOUT,
            resource_type="auth",
            result=AuditLog.RESULT_SUCCESS,
        )

    def _lookup_user(
        self, user_id: int, actor_company_id: Optional[int]
    ) -> User:
        """Load a user, restricting the lookup to the actor's company.

        When ``actor_company_id`` is not None (a company-scoped actor) the
        lookup is scoped in SQL to that company, so a user from another
        company is indistinguishable from a missing user. When it is None the
        actor is a platform-level admin and the unscoped lookup is used.

        Raises:
            ValueError: If the user cannot be found within the actor's scope.
        """
        if actor_company_id is None:
            user = self._user_repository.get_by_id(user_id)
        else:
            user = self._user_repository.get_by_id_for_company(
                user_id, actor_company_id
            )
        if user is None:
            raise ValueError("User not found")
        return user

    def get_user_by_id(
        self, user_id: int, actor_company_id: Optional[int] = None
    ) -> User:
        return self._lookup_user(user_id, actor_company_id)

    def get_user_by_email(self, email: str) -> User:
        user = self._user_repository.get_by_email(email)
        if user is None:
            raise ValueError("User not found")
        return user

    def get_all_users(self) -> List[User]:
        return self._user_repository.get_all()

    def get_all_users_for_company(self, company_id: int) -> List[User]:
        return self._user_repository.get_all_by_company(company_id)

    def create_user(
        self, user_data: dict, actor_company_id: Optional[int] = None
    ) -> User:
        validated = UserValidator.validate_create_user(user_data)

        if actor_company_id is not None:
            validated["company_id"] = actor_company_id

        if self._user_repository.exists_by_username(validated["username"]):
            raise ValueError("Username already exists")

        if self._user_repository.exists_by_email(validated["email"]):
            raise ValueError("Email already exists")

        self._require_valid_company(validated["company_id"])

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

        created = self._user_repository.create(user)
        record_event(
            action=AuditLog.ACTION_CREATE,
            resource_type="user",
            resource_id=str(created.id),
            result=AuditLog.RESULT_SUCCESS,
            company_id=created.company_id,
            after_state=build_snapshot("user", created.to_dict()),
        )
        return created

    def _require_valid_company(self, company_id) -> None:
        """Ensure a company exists before linking a user to it."""
        if not company_id or self._company_repository is None:
            return
        if self._company_repository.get_by_id(company_id) is None:
            raise ValueError("Company not found")

    def update_user(
        self, user_id: int, data: dict, actor_company_id: Optional[int] = None
    ) -> User:
        validated = UserValidator.validate_update_user(data)

        if actor_company_id is not None:
            validated.pop("company_id", None)

        user = self._lookup_user(user_id, actor_company_id)

        if not validated:
            raise ValueError("No valid fields to update")

        before = build_snapshot("user", user.to_dict())

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
            self._require_valid_company(validated["company_id"])
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

        record_event(
            action=AuditLog.ACTION_UPDATE,
            resource_type="user",
            resource_id=str(updated.id),
            result=AuditLog.RESULT_SUCCESS,
            company_id=updated.company_id,
            before_state=before,
            after_state=build_snapshot("user", updated.to_dict()),
        )
        return updated

    def change_password(
        self, user_id: int, new_password: str, actor_company_id: Optional[int] = None
    ) -> User:
        validated = UserValidator.validate_change_password({"new_password": new_password})
        new_password = validated["new_password"]

        user = self._lookup_user(user_id, actor_company_id)

        user.password_hash = hash_password(new_password)

        updated = self._user_repository.update(user)
        if updated is None:
            raise ValueError("Failed to update password")

        record_event(
            action=AuditLog.ACTION_UPDATE,
            resource_type="user",
            resource_id=str(updated.id),
            result=AuditLog.RESULT_SUCCESS,
            company_id=user.company_id,
            metadata={"event": "password_change"},
        )
        return updated

    def activate_user(
        self, user_id: int, actor_company_id: Optional[int] = None
    ) -> User:
        user = self._lookup_user(user_id, actor_company_id)

        before = build_snapshot("user", user.to_dict())
        user.is_active = True
        updated = self._user_repository.update(user)
        if updated is None:
            raise ValueError("Failed to activate user")

        record_event(
            action=AuditLog.ACTION_UPDATE,
            resource_type="user",
            resource_id=str(updated.id),
            result=AuditLog.RESULT_SUCCESS,
            company_id=user.company_id,
            metadata={"event": "activate"},
            before_state=before,
            after_state=build_snapshot("user", updated.to_dict()),
        )
        return updated

    def deactivate_user(
        self, user_id: int, actor_company_id: Optional[int] = None
    ) -> User:
        user = self._lookup_user(user_id, actor_company_id)

        self._guard_last_active_admin(
            user,
            next_role=user.role,
            next_status="inactive",
        )

        before = build_snapshot("user", user.to_dict())
        user.is_active = False
        updated = self._user_repository.update(user)
        if updated is None:
            raise ValueError("Failed to deactivate user")

        record_event(
            action=AuditLog.ACTION_UPDATE,
            resource_type="user",
            resource_id=str(updated.id),
            result=AuditLog.RESULT_SUCCESS,
            company_id=user.company_id,
            metadata={"event": "deactivate"},
            before_state=before,
            after_state=build_snapshot("user", updated.to_dict()),
        )
        return updated

    def delete_user(
        self, user_id: int, actor_company_id: Optional[int] = None
    ) -> bool:
        user = self._lookup_user(user_id, actor_company_id)

        self._guard_last_active_admin(
            user,
            next_role=user.role,
            next_status=user.status,
            removing=True,
        )

        deleted = self._user_repository.delete(user_id)
        if not deleted:
            raise ValueError("User not found")

        record_event(
            action=AuditLog.ACTION_DELETE,
            resource_type="user",
            resource_id=str(user_id),
            result=AuditLog.RESULT_SUCCESS,
            company_id=user.company_id,
            before_state=build_snapshot("user", user.to_dict()),
        )
        return True

    def get_user_settings(self, user_id: int) -> dict:
        """Return the authenticated user's preferences."""
        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        return {
            "language": user.language,
            "theme": user.theme,
            "date_format": user.date_format,
            "number_format": user.number_format,
            "timezone": user.timezone,
            "avatar_path": user.avatar_path,
            "pagination_size": user.pagination_size,
        }

    def update_user_settings(self, user_id: int, data: dict) -> dict:
        """Validate and persist the authenticated user's preferences."""
        validated = SettingsValidator.validate_user_preferences(data)
        updated = self._user_repository.update_preferences(user_id, validated)
        if updated is None:
            raise ValueError("User not found")
        return self.get_user_settings(user_id)

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
            active_admins = self._user_repository.count_active_admins(user.company_id)
            if active_admins <= 1:
                raise ValueError(
                    "Cannot remove, demote, or deactivate the last active admin"
                )