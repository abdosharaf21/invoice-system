"""Audit log model representing a single audited action record."""

from datetime import datetime
from typing import Any, Dict, Optional


class AuditLog:
    """Model for a platform audit trail entry.

    Represents one row in the ``audit_logs`` table. Captures who performed
    an action, what action was performed and against which resource, plus
    the outcome, a JSON metadata payload, the request correlation id, and
    client context (IP address / user agent) so records can be tied back
    to the originating request. Contains no SQL or business logic.

    Attributes:
        ACTION_LOGIN: Audited action for a user login.
        ACTION_LOGOUT: Audited action for a user logout.
        ACTION_CREATE: Audited action for creating a resource.
        ACTION_UPDATE: Audited action for updating a resource.
        ACTION_DELETE: Audited action for deleting a resource.
        ACTION_VIEW: Audited action for reading a resource.
        ACTION_IMPORT: Audited action for an accounting file import.
        ACTION_RECONCILE: Audited action for a reconciliation run.
        ACTION_OTHER: Generic audited action.
        RESULT_SUCCESS: Outcome for a successful operation.
        RESULT_FAILURE: Outcome for a failed operation.
        ACTOR_USER: The action was performed by an authenticated human user.
        ACTOR_SYSTEM: The action was performed by a system/background process.
    """

    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_VIEW = "view"
    ACTION_IMPORT = "import"
    ACTION_RECONCILE = "reconcile"
    ACTION_OTHER = "other"

    RESULT_SUCCESS = "success"
    RESULT_FAILURE = "failure"

    ACTOR_USER = "user"
    ACTOR_SYSTEM = "system"

    def __init__(
        self,
        id: Optional[int] = None,
        actor_id: Optional[int] = None,
        actor_email: Optional[str] = None,
        role: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        result: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        created_at: Optional[datetime] = None,
        company_id: Optional[int] = None,
        actor_type: Optional[str] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize an AuditLog instance.

        Args:
            id: Unique audit log identifier.
            actor_id: ID of the user who performed the action.
            actor_email: Email of the user who performed the action.
            role: Role of the user who performed the action.
            action: One of the ACTION_* constants.
            resource_type: Kind of resource acted upon.
            resource_id: String identifier of the resource acted upon.
            result: One of the RESULT_* constants.
            metadata: Free-form JSON payload with action details.
            request_id: Correlation id from the originating request.
            ip_address: Client IP address, when available.
            user_agent: Client User-Agent header, when available.
            created_at: Timestamp when the action was recorded.
            company_id: Company/tenant the resource belongs to, when any.
            actor_type: One of ACTOR_USER or ACTOR_SYSTEM.
            before_state: Compact structured snapshot before the change.
            after_state: Compact structured snapshot after the change.
        """
        self.id = id
        self.actor_id = actor_id
        self.actor_email = actor_email
        self.role = role
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.result = result
        self.metadata = metadata
        self.request_id = request_id
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.created_at = created_at
        self.company_id = company_id
        self.actor_type = actor_type
        self.before_state = before_state
        self.after_state = after_state

    def to_dict(self) -> Dict[str, Any]:
        """Convert AuditLog instance to a dictionary.

        Returns:
            Dictionary representation of the audit log entry.
        """
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "actor_email": self.actor_email,
            "role": self.role,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "result": self.result,
            "metadata": self.metadata,
            "request_id": self.request_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": (
                self.created_at.isoformat()
                if isinstance(self.created_at, datetime)
                else self.created_at
            ),
            "company_id": self.company_id,
            "actor_type": self.actor_type,
            "before_state": self.before_state,
            "after_state": self.after_state,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLog":
        """Build an AuditLog instance from a dictionary.

        Args:
            data: Dictionary with audit log fields.

        Returns:
            AuditLog instance populated from the data.
        """
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                created_at = None
        return cls(
            id=data.get("id"),
            actor_id=data.get("actor_id"),
            actor_email=data.get("actor_email"),
            role=data.get("role"),
            action=data.get("action"),
            resource_type=data.get("resource_type"),
            resource_id=data.get("resource_id"),
            result=data.get("result"),
            metadata=data.get("metadata"),
            request_id=data.get("request_id"),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
            created_at=created_at,
            company_id=data.get("company_id"),
            actor_type=data.get("actor_type"),
            before_state=data.get("before_state"),
            after_state=data.get("after_state"),
        )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation.

        Returns:
            String describing the audit log entry.
        """
        return (
            f"AuditLog(id={self.id!r}, actor_id={self.actor_id!r}, "
            f"action={self.action!r}, resource_type={self.resource_type!r}, "
            f"resource_id={self.resource_id!r}, result={self.result!r})"
        )