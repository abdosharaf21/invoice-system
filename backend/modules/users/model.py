"""User model representing the users table."""

from datetime import datetime
from typing import Optional


class User:
    """Represents a user record in the users table.

    Attributes:
        id: Unique identifier for the user.
        full_name: User's full name.
        email: User's email address.
        password_hash: Hashed password string.
        phone: User's phone number.
        role: User's role (admin, manager, employee).
        status: User's status (active, inactive).
        created_at: Timestamp when the user was created.
        updated_at: Timestamp when the user was last updated.
    """

    def __init__(
        self,
        id: Optional[int] = None,
        full_name: Optional[str] = None,
        email: Optional[str] = None,
        password_hash: Optional[str] = None,
        phone: Optional[str] = None,
        role: str = "employee",
        status: str = "active",
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ) -> None:
        self.id = id
        self.full_name = full_name
        self.email = email
        self.password_hash = password_hash
        self.phone = phone
        self.role = role
        self.status = status
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "status": self.status,
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

        return cls(
            id=data.get("id"),
            full_name=data.get("full_name"),
            email=data.get("email"),
            password_hash=data.get("password_hash"),
            phone=data.get("phone"),
            role=data.get("role", "employee"),
            status=data.get("status", "active"),
            created_at=created_at,
            updated_at=updated_at
        )

    def __str__(self) -> str:
        return f"User(id={self.id}, name={self.full_name}, email={self.email})"

    def __repr__(self) -> str:
        return self.__str__()
