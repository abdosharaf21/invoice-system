"""Audit trail repository for database operations on audit_logs."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import mysql.connector

from backend.database import Database
from backend.modules.audit_trail.model import AuditLog
from backend.shared.database import db_cursor

logger = logging.getLogger(__name__)

_SAFE_ORDER_COLUMNS = {"id", "created_at", "actor_email", "role", "action"}
_MAX_PAGE_SIZE = 200


class AuditTrailRepository:
    """Repository for audit trail database operations.

    Persists audited actions and reads them back with optional filtering
    and pagination. Uses parameterized queries and the shared connection
    pool. Only allowed to execute SQL.
    """

    def __init__(self, database: Database) -> None:
        """Initialize AuditTrailRepository with a Database instance.

        Args:
            database: Database connection pool manager.
        """
        self._database = database

    def record(
        self,
        actor_id: Optional[int],
        actor_email: Optional[str],
        role: Optional[str],
        action: str,
        resource_type: str,
        resource_id: Optional[str],
        result: str,
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        company_id: Optional[int] = None,
        actor_type: str = "user",
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Insert a single audit log entry.

        Args:
            actor_id: ID of the acting user, or None for system actions.
            actor_email: Email of the acting user, or None.
            role: Role of the acting user, or None.
            action: Audited action verb (e.g. login, create).
            resource_type: Kind of resource acted upon.
            resource_id: String identifier of the resource acted upon.
            result: Outcome of the action (success or failure).
            metadata: Optional free-form JSON payload.
            request_id: Optional correlation id for the request.
            ip_address: Optional client IP address.
            user_agent: Optional client User-Agent header.
            company_id: Optional company/tenant the resource belongs to.
            actor_type: 'user' or 'system' actor classification.
            before_state: Optional compact structured snapshot (before).
            after_state: Optional compact structured snapshot (after).

        Returns:
            The generated audit log id.

        Raises:
            mysql.connector.Error: If the insert fails.
        """
        metadata_json = json.dumps(metadata) if metadata is not None else None
        before_json = json.dumps(before_state) if before_state is not None else None
        after_json = json.dumps(after_state) if after_state is not None else None
        with self._database.connection() as conn, db_cursor(conn) as cursor:
            try:
                cursor.execute(
                    "INSERT INTO audit_logs "
                    "(actor_id, actor_email, role, action, resource_type, "
                    "resource_id, result, metadata, request_id, ip_address, "
                    "user_agent, company_id, actor_type, before_state, "
                    "after_state) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s)",
                    (
                        actor_id,
                        actor_email,
                        role,
                        action,
                        resource_type,
                        resource_id,
                        result,
                        metadata_json,
                        request_id,
                        ip_address,
                        user_agent,
                        company_id,
                        actor_type,
                        before_json,
                        after_json,
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid)
            except mysql.connector.Error:
                conn.rollback()
                raise

    def list_logs(
        self,
        filters: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List audit logs with filtering and pagination.

        Supported filters: company_id, actor_id, action, resource_type,
        result, start_date, end_date. When a company_id is provided the
        query is scoped to that company plus company-wide (NULL tenancy)
        events; unscoped queries (company_id None/0) return the full stream
        and are only used by the service when the caller is not tenant-bound.
        Results are ordered newest-first.

        Args:
            filters: Dictionary with optional actor_id, action,
                resource_type, result, company_id, start_date, end_date,
                page, and page_size keys.

        Returns:
            A tuple of (list of audit log dictionaries, total count).

        Raises:
            mysql.connector.Error: If the query fails.
        """
        where_clauses = []
        params: List[Any] = []

        company_id = filters.get("company_id")
        if company_id is not None:
            company_id = int(company_id)
            if company_id > 0:
                where_clauses.append(
                    "(company_id = %s OR company_id IS NULL)"
                )
                params.append(company_id)
            else:
                where_clauses.append("company_id IS NULL")
        if filters.get("actor_id") is not None:
            where_clauses.append("actor_id = %s")
            params.append(int(filters["actor_id"]))
        if filters.get("action"):
            where_clauses.append("action = %s")
            params.append(filters["action"])
        if filters.get("resource_type"):
            where_clauses.append("resource_type = %s")
            params.append(filters["resource_type"])
        if filters.get("result"):
            where_clauses.append("result = %s")
            params.append(filters["result"])
        if filters.get("start_date"):
            where_clauses.append("created_at >= %s")
            params.append(filters["start_date"])
        if filters.get("end_date"):
            where_clauses.append("created_at <= %s")
            params.append(filters["end_date"])

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        page = max(int(filters.get("page", 1)), 1)
        page_size = min(max(int(filters.get("page_size", 50)), 1), _MAX_PAGE_SIZE)
        offset = (page - 1) * page_size

        with self._database.connection() as conn, db_cursor(
            conn, dictionary=True
        ) as cursor:
            try:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM audit_logs {where_sql}",
                    params,
                )
                row = cursor.fetchone()
                total = int(row["total"]) if row else 0

                order_col = filters.get("sort_by", "created_at")
                if order_col not in _SAFE_ORDER_COLUMNS:
                    order_col = "created_at"

                cursor.execute(
                    f"SELECT id, actor_id, actor_email, role, action, "
                    f"resource_type, resource_id, result, metadata, "
                    f"request_id, ip_address, user_agent, created_at, "
                    f"company_id, actor_type, before_state, after_state "
                    f"FROM audit_logs {where_sql} "
                    f"ORDER BY {order_col} DESC, id DESC "
                    f"LIMIT %s OFFSET %s",
                    params + [page_size, offset],
                )
                rows = cursor.fetchall()
            except mysql.connector.Error:
                raise

        return [self._row_to_dict(row) for row in rows], total

    @staticmethod
    def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a database row to an audit log dictionary.

        Args:
            row: Database row as a dictionary.

        Returns:
            Audit log dictionary with parsed metadata.
        """
        def _parse_json(value: Any) -> Any:
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (ValueError, TypeError):
                    return None
            return value

        metadata = _parse_json(row.get("metadata"))
        before_state = _parse_json(row.get("before_state"))
        after_state = _parse_json(row.get("after_state"))
        created_at = row.get("created_at")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        return {
            "id": row["id"],
            "actor_id": row.get("actor_id"),
            "actor_email": row.get("actor_email"),
            "role": row.get("role"),
            "action": row.get("action"),
            "resource_type": row.get("resource_type"),
            "resource_id": row.get("resource_id"),
            "result": row.get("result"),
            "metadata": metadata,
            "request_id": row.get("request_id"),
            "ip_address": row.get("ip_address"),
            "user_agent": row.get("user_agent"),
            "created_at": created_at,
            "company_id": row.get("company_id"),
            "actor_type": row.get("actor_type"),
            "before_state": before_state,
            "after_state": after_state,
        }