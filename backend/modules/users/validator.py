"""User validator for user input validation."""

import re
from typing import Dict, Any


class UserValidator:
    """Validator for user input data.

    Handles all validation logic for user-related operations.
    """

    VALID_ROLES = ["admin", "manager", "employee"]
    VALID_STATUSES = ["active", "inactive"]
    EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    PHONE_REGEX = r'^\+?[0-9]{10,15}$'
    MIN_PASSWORD_LENGTH = 8
    MAX_NAME_LENGTH = 100
    MAX_EMAIL_LENGTH = 150
    MAX_PHONE_LENGTH = 20

    @staticmethod
    def validate_email(email: str) -> str:
        if not email:
            raise ValueError("Email is required")

        email = email.strip()

        if len(email) > UserValidator.MAX_EMAIL_LENGTH:
            raise ValueError(f"Email must not exceed {UserValidator.MAX_EMAIL_LENGTH} characters")

        if not re.match(UserValidator.EMAIL_REGEX, email):
            raise ValueError("Invalid email format")

        return email

    @staticmethod
    def validate_phone(phone: str) -> str:
        if not phone:
            return None

        phone = phone.strip()

        if len(phone) > UserValidator.MAX_PHONE_LENGTH:
            raise ValueError(f"Phone must not exceed {UserValidator.MAX_PHONE_LENGTH} characters")

        if not re.match(UserValidator.PHONE_REGEX, phone):
            raise ValueError("Invalid phone format")

        return phone

    @staticmethod
    def validate_name(name: str) -> str:
        if not name:
            raise ValueError("Name is required")

        name = name.strip()

        if len(name) == 0:
            raise ValueError("Name cannot be empty")

        if len(name) > UserValidator.MAX_NAME_LENGTH:
            raise ValueError(f"Name must not exceed {UserValidator.MAX_NAME_LENGTH} characters")

        return name

    @staticmethod
    def validate_password(password: str) -> str:
        if not password:
            raise ValueError("Password is required")

        if len(password) < UserValidator.MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {UserValidator.MIN_PASSWORD_LENGTH} characters")

        return password

    @staticmethod
    def validate_role(role: str) -> str:
        if not role:
            return "employee"

        role = role.strip().lower()

        if role not in UserValidator.VALID_ROLES:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(UserValidator.VALID_ROLES)}")

        return role

    @staticmethod
    def validate_status(status: str) -> str:
        if not status:
            return "active"

        status = status.strip().lower()

        if status not in UserValidator.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(UserValidator.VALID_STATUSES)}")

        return status

    @staticmethod
    def validate_login(data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            raise ValueError("Login data is required")

        if "email" not in data:
            raise ValueError("Email is required")

        if "password" not in data:
            raise ValueError("Password is required")

        return {
            "email": UserValidator.validate_email(data["email"]),
            "password": data["password"]
        }

    @staticmethod
    def validate_create_user(data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            raise ValueError("User data is required")

        validated = {
            "full_name": UserValidator.validate_name(data.get("full_name")),
            "email": UserValidator.validate_email(data.get("email")),
            "password": UserValidator.validate_password(data.get("password")),
            "phone": UserValidator.validate_phone(data.get("phone")),
            "role": UserValidator.validate_role(data.get("role")),
            "status": UserValidator.validate_status(data.get("status"))
        }

        return validated

    @staticmethod
    def validate_update_user(data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            raise ValueError("Update data is required")

        validated = {}

        if "full_name" in data:
            validated["full_name"] = UserValidator.validate_name(data["full_name"])

        if "email" in data:
            validated["email"] = UserValidator.validate_email(data["email"])

        if "phone" in data:
            validated["phone"] = UserValidator.validate_phone(data["phone"])

        if "role" in data:
            validated["role"] = UserValidator.validate_role(data["role"])

        if "status" in data:
            validated["status"] = UserValidator.validate_status(data["status"])

        if not validated:
            raise ValueError("No valid fields to update")

        return validated

    @staticmethod
    def validate_change_password(data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            raise ValueError("Password data is required")

        if "new_password" not in data:
            raise ValueError("New password is required")

        return {
            "new_password": UserValidator.validate_password(data["new_password"])
        }
