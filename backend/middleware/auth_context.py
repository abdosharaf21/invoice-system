"""Authentication context middleware for storing user info in g."""

from flask import g
from flask_jwt_extended import get_jwt_identity, get_jwt, verify_jwt_in_request


def load_user_context() -> None:
    """Load authenticated user information into Flask's g context.

    Extracts user ID, email, role, full_name and company_id from the JWT
    token and stores them in Flask's g object for use in routes.
    """
    try:
        verify_jwt_in_request()
        jwt_data = get_jwt()
        user_id = get_jwt_identity()

        g.user_id = int(user_id) if user_id else None
        g.user_email = jwt_data.get("email")
        g.user_role = jwt_data.get("role")
        g.user_full_name = jwt_data.get("full_name")
        company_id = jwt_data.get("company_id")
        g.user_company_id = int(company_id) if company_id is not None else None
    except Exception:
        g.user_id = None
        g.user_email = None
        g.user_role = None
        g.user_full_name = None
        g.user_company_id = None


def clear_user_context() -> None:
    """Clear user information from Flask's g context."""
    g.user_id = None
    g.user_email = None
    g.user_role = None
    g.user_full_name = None
    g.user_company_id = None


def get_current_user_id() -> int:
    """Get the current authenticated user's ID from g context."""
    return getattr(g, "user_id", None)


def get_current_user_email() -> str:
    """Get the current authenticated user's email from g context."""
    return getattr(g, "user_email", None)


def get_current_user_role() -> str:
    """Get the current authenticated user's role from g context."""
    return getattr(g, "user_role", None)


def get_current_user_full_name() -> str:
    """Get the current authenticated user's full name from g context."""
    return getattr(g, "user_full_name", None)


def get_current_user_company_id() -> int:
    """Get the current authenticated user's company id from g context."""
    return getattr(g, "user_company_id", None)
