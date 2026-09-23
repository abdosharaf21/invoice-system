"""Audit trail service for recording and querying audited actions."""

import logging
from typing import Any, Dict, Optional

from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.repository import AuditTrailRepository

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {
    AuditLog.ACTION_LOGIN,
    AuditLog.ACTION_LOGOUT,
    AuditLog.ACTION_CREATE,
    AuditLog.ACTION_UPDATE,
    AuditLog.ACTION_DELETE,
    AuditLog.ACTION_VIEW,
    AuditLog.ACTION_IMPORT,
    AuditLog.ACTION_RECONCILE,
    AuditLog.ACTION_OTHER,
}
_VALID_RESULTS = {AuditLog.RESULT_SUCCESS, AuditLog.RESULT_FAILURE}
_VALID_ACTOR_TYPES = {AuditLog.ACTOR_USER, AuditLog.ACTOR_SYSTEM}

_SENSITIVE_TERMS = ("password", "secret", "token", "api_key", "authorization")

# Whitelisted fields for compact before/after snapshots. Unknown resource
# types or fields are rejected rather than serialized, so no arbitrary row
# is ever mirrored into the audit trail.
_SNAPSHOT_FIELDS: Dict[str, frozenset] = {
    "user": frozenset({
        "id", "username", "email", "first_name", "last_name", "is_active",
        "roles", "company_id", "status",
    }),
    "company": frozenset({
        "id", "name", "email", "phone", "address", "is_active",
        "default_currency", "default_tax_rate", "fiscal_year_start",
        "tax_registration_number",
    }),
    "setting": frozenset({
        "setting_key", "setting_value", "value_type", "description",
    }),
    "import": frozenset({
        "id", "company_id", "filename", "file_type", "status",
        "total_rows", "processed_rows", "error_rows",
    }),
    "reconciliation": frozenset({
        "id", "company_id", "period", "status",
    }),
}

_configured_service: Optional["AuditTrailService"] = None
_audit_enabled: bool = True


def set_audit_trail_service(service: Optional["AuditTrailService"]) -> None:
    """Register the platform-wide audit trail service instance.

    Called during application wiring so that other services and
    middleware can record audit events without constructing their own
    repository connections.

    Args:
        service: The configured AuditTrailService instance, or None.
    """
    global _configured_service
    _configured_service = service


def get_audit_trail_service() -> Optional["AuditTrailService"]:
    """Return the registered audit trail service, if any.

    Returns:
        The configured AuditTrailService instance, or None when the
        application has not been fully wired (e.g. in tests).
    """
    return _configured_service


def set_audit_enabled(enabled: bool) -> None:
    """Enable or disable audit recording at runtime.

    Acts as a global kill-switch read from application configuration.
    When disabled, ``record_event`` and ``record_security_event`` become
    no-ops and the primary operations are never affected.

    Args:
        enabled: Whether audit recording is allowed.
    """
    global _audit_enabled
    _audit_enabled = bool(enabled)


def build_snapshot(resource_type: str, data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Build a redacted, whitelisted snapshot of a resource.

    Only the fields declared for the resource type are kept; nothing else is
    copied. Secrets (passwords, tokens, hashes, API keys) are always dropped
    even if a whitelist accidentally matched a sensitive name.

    Args:
        resource_type: One of the known snapshot resource types, or None.
        data: The resource dictionary (usually a model ``to_dict()``).

    Returns:
        A compact dictionary or None when the resource type is unknown or
        the input is empty.
    """
    if not data:
        return None
    allowed = _SNAPSHOT_FIELDS.get(resource_type)
    if allowed is None:
        return None
    snapshot: Dict[str, Any] = {}
    for key, value in data.items():
        if key not in allowed:
            continue
        lowered = key.lower()
        if any(term in lowered for term in _SENSITIVE_TERMS):
            continue
        snapshot[key] = value
    return snapshot if snapshot else None


def record_event(
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    result: str = AuditLog.RESULT_SUCCESS,
    metadata: Optional[Dict[str, Any]] = None,
    actor_id: Optional[int] = None,
    actor_email: Optional[str] = None,
    role: Optional[str] = None,
    company_id: Optional[int] = None,
    actor_type: Optional[str] = None,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Record a business/administrative event without disrupting the caller.

    When explicit actor attributes or a company are supplied they are
    recorded verbatim; otherwise they are derived from the current request
    context. Any failure to write the audit entry is logged and swallowed so
    the primary business operation still completes.

    Args:
        action: One of the AuditLog.ACTION_* verbs.
        resource_type: Kind of resource acted upon.
        resource_id: Optional resource identifier.
        result: One of the AuditLog.RESULT_* outcomes.
        metadata: Optional JSON-serializable metadata.
        actor_id: Optional explicit acting user id.
        actor_email: Optional explicit acting user email.
        role: Optional explicit acting user role.
        company_id: Optional explicit company/tenant attribution.
        actor_type: Optional 'user' or 'system' actor classification.
        before_state: Optional compact snapshot of the resource before.
        after_state: Optional compact snapshot of the resource after.

    Returns:
        The new audit log id, or None when auditing is unavailable or
        fails.
    """
    return _record(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        metadata=metadata,
        actor_id=actor_id,
        actor_email=actor_email,
        role=role,
        company_id=company_id,
        actor_type=actor_type,
        before_state=before_state,
        after_state=after_state,
    )


def record_security_event(
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    result: str = AuditLog.RESULT_SUCCESS,
    metadata: Optional[Dict[str, Any]] = None,
    actor_id: Optional[int] = None,
    actor_email: Optional[str] = None,
    role: Optional[str] = None,
    company_id: Optional[int] = None,
    actor_type: Optional[str] = None,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Record a security-relevant event without disrupting the caller.

    Behaviour is identical to :func:`record_event`; this alias exists so
    call sites communicate their intent clearly.

    Args:
        action: One of the AuditLog.ACTION_* verbs.
        resource_type: Kind of resource acted upon.
        resource_id: Optional resource identifier.
        result: One of the AuditLog.RESULT_* outcomes.
        metadata: Optional JSON-serializable metadata.
        actor_id: Optional explicit acting user id.
        actor_email: Optional explicit acting user email.
        role: Optional explicit acting user role.
        company_id: Optional explicit company/tenant attribution.
        actor_type: Optional 'user' or 'system' actor classification.
        before_state: Optional compact snapshot of the resource before.
        after_state: Optional compact snapshot of the resource after.

    Returns:
        The new audit log id, or None when auditing is unavailable or
        fails.
    """
    return _record(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        metadata=metadata,
        actor_id=actor_id,
        actor_email=actor_email,
        role=role,
        company_id=company_id,
        actor_type=actor_type,
        before_state=before_state,
        after_state=after_state,
    )


def _record(
    action: str,
    resource_type: str,
    resource_id: Optional[str],
    result: str,
    metadata: Optional[Dict[str, Any]],
    actor_id: Optional[int],
    actor_email: Optional[str],
    role: Optional[str],
    company_id: Optional[int],
    actor_type: Optional[str],
    before_state: Optional[Dict[str, Any]],
    after_state: Optional[Dict[str, Any]],
) -> Optional[int]:
    """Shared implementation for record helpers.

    Returns:
        The new audit log id, or None when auditing is unavailable or
        fails.
    """
    if not _audit_enabled:
        return None
    service = get_audit_trail_service()
    if service is None:
        return None
    try:
        if actor_id is not None or actor_email is not None:
            return service.record(
                actor_id=actor_id,
                actor_email=actor_email,
                role=role,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result=result,
                metadata=metadata,
                request_id=_request_id_or_none(),
                ip_address=_request_ip_or_none(),
                user_agent=_request_user_agent_or_none(),
                company_id=company_id,
                actor_type=actor_type,
                before_state=before_state,
                after_state=after_state,
            )
        return service.record_from_context(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            metadata=metadata,
            company_id=company_id,
            actor_type=actor_type,
            before_state=before_state,
            after_state=after_state,
        )
    except Exception:
        logger.warning(
            "Audit event %s/%s could not be recorded; continuing",
            resource_type,
            action,
            exc_info=True,
        )
        return None


class AuditTrailService:
    """Service for audit trail business operations.

    Records audited actions (with actor, resource, and outcome) and lists
    them back with filtering and pagination. Contains validation and
    orchestration only — data access is delegated to
    :class:`AuditTrailRepository`. Records can be produced either with
    explicit actor attributes or derived from the current request context.
    """

    def __init__(self, audit_repository: AuditTrailRepository) -> None:
        """Initialize AuditTrailService with an AuditTrailRepository.

        Args:
            audit_repository: Repository for audit trail database operations.
        """
        self._repository = audit_repository

    def record(
        self,
        actor_id: Optional[int],
        actor_email: Optional[str],
        role: Optional[str],
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        result: str = AuditLog.RESULT_SUCCESS,
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        company_id: Optional[int] = None,
        actor_type: Optional[str] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record an audited action.

        Args:
            actor_id: ID of the acting user, or None.
            actor_email: Email of the acting user, or None.
            role: Role of the acting user, or None.
            action: One of the AuditLog.ACTION_* verbs.
            resource_type: Kind of resource acted upon.
            resource_id: String identifier of the resource acted upon.
            result: One of the AuditLog.RESULT_* outcomes.
            metadata: Optional free-form payload describing the action.
            request_id: Optional correlation id for the request.
            ip_address: Optional client IP address.
            user_agent: Optional client User-Agent header.
            company_id: Optional company/tenant attribution.
            actor_type: Optional 'user' or 'system' actor classification.
            before_state: Optional compact snapshot of the resource before.
            after_state: Optional compact snapshot of the resource after.

        Returns:
            The id of the newly created audit log.

        Raises:
            ValueError: If the action, result or actor type is not valid.
        """
        if action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid audit action. Must be one of: "
                f"{', '.join(sorted(_VALID_ACTIONS))}"
            )
        if result not in _VALID_RESULTS:
            raise ValueError(
                f"Invalid audit result. Must be one of: "
                f"{', '.join(sorted(_VALID_RESULTS))}"
            )
        actor_type = actor_type or AuditLog.ACTOR_USER
        if actor_type not in _VALID_ACTOR_TYPES:
            raise ValueError(
                f"Invalid audit actor_type. Must be one of: "
                f"{', '.join(sorted(_VALID_ACTOR_TYPES))}"
            )

        return self._repository.record(
            actor_id=actor_id,
            actor_email=actor_email,
            role=role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            metadata=metadata,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            company_id=company_id,
            actor_type=actor_type,
            before_state=before_state,
            after_state=after_state,
        )

    def record_from_context(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        result: str = AuditLog.RESULT_SUCCESS,
        metadata: Optional[Dict[str, Any]] = None,
        company_id: Optional[int] = None,
        actor_type: Optional[str] = None,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record an audited action using the current request context.

        Reads the actor (id, email, role), the company attribution, the
        correlation request id, and client context (IP, User-Agent) from the
        active request. Outside a request context the optional fields degrade
        to None. Call this only from within an active request context when
        actor attribution matters.

        Args:
            action: One of the AuditLog.ACTION_* verbs.
            resource_type: Kind of resource acted upon.
            resource_id: String identifier of the resource acted upon.
            result: One of the AuditLog.RESULT_* outcomes.
            metadata: Optional free-form payload describing the action.
            company_id: Optional explicit company attribution; when unset it
                is derived from the authenticated request context.
            actor_type: Optional 'user' or 'system' actor classification.
            before_state: Optional compact snapshot of the resource before.
            after_state: Optional compact snapshot of the resource after.

        Returns:
            The id of the newly created audit log.

        Raises:
            ValueError: If the action or result is not valid.
        """
        return self.record(
            actor_id=self._actor_id(),
            actor_email=self._actor_email(),
            role=self._actor_role(),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            metadata=metadata,
            request_id=self._request_id(),
            ip_address=self._request_ip(),
            user_agent=self._request_user_agent(),
            company_id=company_id if company_id is not None else self._request_company_id(),
            actor_type=actor_type or AuditLog.ACTOR_USER,
            before_state=before_state,
            after_state=after_state,
        )

    def list_logs(
        self,
        actor_id: Optional[int] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        result: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: Optional[str] = None,
        company_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List audit logs with filtering and pagination.

        Args:
            actor_id: Optional filter by acting user id.
            action: Optional filter by action verb.
            resource_type: Optional filter by resource type.
            result: Optional filter by outcome.
            page: Page number, starting at 1.
            page_size: Number of entries per page.
            sort_by: Optional allowed sort column.
            company_id: Optional company/tenant scope (tenant isolation).
            start_date: Optional inclusive created_at lower bound (YYYY-MM-DD).
            end_date: Optional inclusive created_at upper bound (YYYY-MM-DD).

        Returns:
            Dictionary with items, total, page, page_size, and pages.

        Raises:
            ValueError: If an invalid action, result or date filter is given.
        """
        if action is not None and action not in _VALID_ACTIONS:
            raise ValueError(
                f"Invalid audit action filter. Must be one of: "
                f"{', '.join(sorted(_VALID_ACTIONS))}"
            )
        if result is not None and result not in _VALID_RESULTS:
            raise ValueError(
                f"Invalid audit result filter. Must be one of: "
                f"{', '.join(sorted(_VALID_RESULTS))}"
            )
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")

        filters = {
            "actor_id": actor_id,
            "action": action,
            "resource_type": resource_type,
            "result": result,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "company_id": company_id,
            "start_date": start_date,
            "end_date": end_date,
        }
        items, total = self._repository.list_logs(filters)
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": total_pages,
            "total_pages": total_pages,
        }

    @staticmethod
    def _validate_date(value: Optional[str], name: str) -> None:
        """Validate an inclusive date filter value, if provided."""
        if value is None:
            return
        from datetime import date as _date
        try:
            _date.fromisoformat(value)
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid {name}. Expected a YYYY-MM-DD date."
            )

    # ------------------------------------------------------------------
    # Request-context helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _actor_id() -> Optional[int]:
        """Return the acting user id from Flask's g, if present."""
        try:
            from backend.middleware.auth_context import get_current_user_id
            return get_current_user_id()
        except Exception:
            return None

    @staticmethod
    def _actor_email() -> Optional[str]:
        """Return the acting user email from Flask's g, if present."""
        try:
            from backend.middleware.auth_context import get_current_user_email
            return get_current_user_email()
        except Exception:
            return None

    @staticmethod
    def _actor_role() -> Optional[str]:
        """Return the acting user role from Flask's g, if present."""
        try:
            from backend.middleware.auth_context import get_current_user_role
            return get_current_user_role()
        except Exception:
            return None

    @staticmethod
    def _request_company_id() -> Optional[int]:
        """Return the acting user's company id from Flask's g, if present.

        The value is derived from the signed JWT (never from client input),
        so tenant attribution always comes from authoritative server-side
        state.
        """
        try:
            from flask import g
            value = getattr(g, "user_company_id", None)
            return int(value) if value is not None else None
        except Exception:
            return None

    @staticmethod
    def _request_id() -> Optional[str]:
        """Return the correlation request id from Flask's g, if present."""
        try:
            from backend.middleware import get_request_id
            return get_request_id() or None
        except Exception:
            return None

    @staticmethod
    def _request_ip() -> Optional[str]:
        """Return the client IP address, preferring a proxy-declared header."""
        try:
            from flask import request
            return (
                request.headers.get("X-Real-IP")
                or request.remote_addr
                or None
            )
        except Exception:
            return None

    @staticmethod
    def _request_user_agent() -> Optional[str]:
        """Return the client User-Agent header, if present."""
        try:
            from flask import request
            return request.user_agent.string or None
        except Exception:
            return None


def _request_id_or_none() -> Optional[str]:
    """Return the current request correlation id, if inside a request."""
    try:
        from backend.middleware import get_request_id
        return get_request_id() or None
    except Exception:
        return None


def _request_ip_or_none() -> Optional[str]:
    """Return the current client IP address, if inside a request."""
    try:
        from flask import request
        return (
            request.headers.get("X-Real-IP")
            or request.remote_addr
            or None
        )
    except Exception:
        return None


def _request_user_agent_or_none() -> Optional[str]:
    """Return the current client User-Agent, if inside a request."""
    try:
        from flask import request
        return request.user_agent.string or None
    except Exception:
        return None