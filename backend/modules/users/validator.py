"""User validator for user input validation."""

import re
from typing import Any, Dict, List


class UserValidator:
    """Validator for user input data.

    Handles all validation logic for user-related operations.
    Roles are validated against the platform's seeded role names.
    """

    VALID_ROLES = ["admin", "accountant", "manager", "viewer"]
    VALID_STATUSES = ["active", "inactive"]
    EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    USERNAME_REGEX = r'^[a-zA-Z0-9_.-]+$'
    MIN_PASSWORD_LENGTH = 8
    MAX_USERNAME_LENGTH = 100
    MAX_NAME_LENGTH = 100
    MAX_EMAIL_LENGTH = 150

    @staticmethod
    def validate_email(email: str) -> str:
        if not email:
            raise ValueError("Email is required")

        email = email.strip().lower()

        if len(email) > UserValidator.MAX_EMAIL_LENGTH:
            raise ValueError(f"Email must not exceed {UserValidator.MAX_EMAIL_LENGTH} characters")

        if not re.match(UserValidator.EMAIL_REGEX, email):
            raise ValueError("Invalid email format")

        return email

    @staticmethod
    def validate_username(username: str) -> str:
        if not username:
            raise ValueError("Username is required")

        username = username.strip().lower()

        if len(username) > UserValidator.MAX_USERNAME_LENGTH:
            raise ValueError(f"Username must not exceed {UserValidator.MAX_USERNAME_LENGTH} characters")

        if not re.match(UserValidator.USERNAME_REGEX, username):
            raise ValueError("Username may only contain letters, numbers, dots, dashes and underscores")

        return username

    @staticmethod
    def validate_name(name: str, field: str = "Name") -> List:
        if not name:
            return None

        name = name.strip()

        if len(name) == 0:
            raise ValueError(f"{field} cannot be empty")

        if len(name) > UserValidator.MAX_NAME_LENGTH:
            raise ValueError(f"{field} must not exceed {UserValidator.MAX_NAME_LENGTH} characters")

        return name

    @staticmethod
    def validate_password(password: str) -> str:
        if not password:
            raise ValueError("Password is required")

        if len(password) < UserValidator.MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {UserValidator.MIN_PASSWORD_LENGTH} characters")

        return password

    @staticmethod
    def validate_roles(roles) -> List[str]:
        """Validate a list of role names against the seeded roles.

        Returns an empty list when no roles are provided; the caller
        decides the default role.
        """
        if not roles:
            return []

        if not isinstance(roles, list):
            raise ValueError("Roles must be a list")

        cleaned = []
        for role in roles:
            role = str(role).strip().lower()
            if not role:
                continue
            if role not in UserValidator.VALID_ROLES:
                raise ValueError(
                    f"Invalid role. Must be one of: {', '.join(UserValidator.VALID_ROLES)}"
                )
            cleaned.append(role)

        return cleaned

    @staticmethod
    def validate_company_id(company_id) -> Any:
        if company_id in (None, ""):
            return None

        try:
            return int(company_id)
        except (ValueError, TypeError):
            raise ValueError("Company ID must be an integer")

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
            "username": UserValidator.validate_username(data.get("username")),
            "email": UserValidator.validate_email(data.get("email")),
            "password": UserValidator.validate_password(data.get("password")),
            "first_name": UserValidator.validate_name(data.get("first_name"), "First name"),
            "last_name": UserValidator.validate_name(data.get("last_name"), "Last name"),
            "company_id": UserValidator.validate_company_id(data.get("company_id")),
            "roles": UserValidator.validate_roles(data.get("roles")),
            "status": UserValidator.validate_status(data.get("status"))
        }

        return validated

    @staticmethod
    def validate_update_user(data: Dict[str, Any]) -> Dict[str, Any]:
        if not data:
            raise ValueError("Update data is required")

        user_validator = UserValidator
        validated: Dict[str, Any] = {}

        if "username" in data:
            validated["username"] = user_validator.validate_username(data["username"])

        if "email" in data:
            validated["email"] = user_validator.validate_email(data["email"])

        if "first_name" in data:
            validated["first_name"] = user_validator.validate_name(data["first_name"], "First name")

        if "last_name" in data:
            validated["last_name"] = user_validator.validate_name(data["last_name"], "Last name")

        if "company_id" in data:
            validated["company_id"] = user_validator.validate_company_id(data["company_id"])

        if "roles" in data:
            validated["roles"] = user_validator.validate_roles(data["roles"])

        if "status" in data:
            validated["status"] = user_validator.validate_status(data["status"])

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