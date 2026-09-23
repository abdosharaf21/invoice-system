"""Company model representing the companies table."""

from datetime import datetime
from typing import Optional


class Company:
    """Represents a company record in the companies table.

    Attributes:
        id: Unique identifier for the company.
        name: Registered legal name of the company.
        tax_registration_number: VAT/tax registration number (unique).
        email: Contact email address.
        phone: Contact phone number.
        address: Registered address.
        is_active: Whether the company is active.
        created_at: Timestamp when the company was created.
        updated_at: Timestamp when the company was last updated.
    """

    def __init__(
        self,
        id: Optional[int] = None,
        name: Optional[str] = None,
        tax_registration_number: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
        is_active: bool = True,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        logo_path: Optional[str] = None,
        website: Optional[str] = None,
        default_currency: str = "EGP",
        default_tax_rate: float = 0.0,
        fiscal_year_start: str = "01-01",
    ) -> None:
        self.id = id
        self.name = name
        self.tax_registration_number = tax_registration_number
        self.email = email
        self.phone = phone
        self.address = address
        self.is_active = is_active
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
        self.logo_path = logo_path
        self.website = website
        self.default_currency = default_currency
        self.default_tax_rate = default_tax_rate
        self.fiscal_year_start = fiscal_year_start

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "tax_registration_number": self.tax_registration_number,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "logo_path": self.logo_path,
            "website": self.website,
            "default_currency": self.default_currency,
            "default_tax_rate": self.default_tax_rate,
            "fiscal_year_start": self.fiscal_year_start,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Company":
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = data.get("updated_at")
        if updated_at and isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            id=data.get("id"),
            name=data.get("name"),
            tax_registration_number=data.get("tax_registration_number"),
            email=data.get("email"),
            phone=data.get("phone"),
            address=data.get("address"),
            is_active=bool(data.get("is_active", True)),
            created_at=created_at,
            updated_at=updated_at
        )

    def __str__(self) -> str:
        return f"Company(id={self.id}, name={self.name})"

    def __repr__(self) -> str:
        return self.__str__()