"""User model representing the users table."""

from datetime import datetime
from typing import List, Optional


class User:
    """Represents a user record in the users table.

    Attributes:
        id: Unique identifier for the user.
        company_id: Company the user belongs to (None for platform-level
            admins).
        username: Unique login/username.
        email: User's email address (used for authentication).
        password_hash: Hashed password string.
        first_name: User's first name.
        last_name: User's last name.
        is_active: Whether the account is active.
        roles: List of role names assigned to the user.
        last_login_at: Timestamp of the last successful login.
        created_at: Timestamp when the user was created.
        updated_at: Timestamp when the user was last updated.
    """

    def __init__(
        self,
        id: Optional[int] = None,
        company_id: Optional[int] = None,
        username: Optional[str] = None,
        email: Optional[str] = None,
        password_hash: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        is_active: bool = True,
        roles: Optional[List[str]] = None,
        last_login_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.company_id = company_id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.first_name = first_name
        self.last_name = last_name
        self.is_active = is_active
        self.roles = roles if roles is not None else []
        self.last_login_at = last_login_at
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    @property
    def full_name(self) -> str:
        """Full name assembled from first and last name."""
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()

    @property
    def role(self) -> Optional[str]:
        """Primary role, used for JWT claims and RBAC."""
        return self.roles[0] if self.roles else None

    @property
    def status(self) -> str:
        """Human-readable account status derived from is_active."""
        return "active" if self.is_active else "inactive"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "username": self.username,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "roles": list(self.roles),
            "is_active": self.is_active,
            "status": self.status,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = data.get("updated_at")
        if updated_at and isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        last_login_at = data.get("last_login_at")
        if last_login_at and isinstance(last_login_at, str):
            last_login_at = datetime.fromisoformat(last_login_at)

        status = data.get("status", "active")
        is_active = data.get("is_active", status == "active")

        return cls(
            id=data.get("id"),
            company_id=data.get("company_id"),
            username=data.get("username"),
            email=data.get("email"),
            password_hash=data.get("password_hash"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            is_active=bool(is_active),
            roles=list(data.get("roles") or []),
            last_login_at=last_login_at,
            created_at=created_at,
            updated_at=updated_at
        )

    def __str__(self) -> str:
        return f"User(id={self.id}, name={self.full_name}, email={self.email})"

    def __repr__(self) -> str:
        return self.__str__()