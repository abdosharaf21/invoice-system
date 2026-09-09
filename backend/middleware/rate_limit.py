"""Lightweight in-memory rate limiting middleware.

Implements a fixed-window counter keyed by a client identifier (by
default the remote IP, optionally combined with an endpoint category).
Protects sensitive endpoints from brute-force and denial-of-service abuse.
"""

import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from flask import jsonify, request

SENSITIVE_ENDPOINTS = {
    "/api/auth/login": "login",
    "/api/auth/refresh": "refresh",
    "/api/auth/change-password": "password",
}


def classify_request(path: str) -> Optional[str]:
    """Map a request path to a rate-limit category, if any."""
    if path in SENSITIVE_ENDPOINTS:
        return SENSITIVE_ENDPOINTS[path]
    if path.endswith("/change-password") or path.endswith("/password"):
        return "password"
    return None


class RateLimiter:
    """In-memory fixed-window rate limiter with per-category config."""

    def __init__(
        self,
        limits: Optional[Dict[str, Tuple[int, int]]] = None,
        exempt_ip_prefixes: Optional[List[str]] = None,
    ) -> None:
        self._limits = limits or {
            "login": (5, 60),      # 5 attempts per minute
            "refresh": (30, 60),   # 30 refreshes per minute
            "password": (5, 60),   # 5 password changes per minute
        }
        self._exempt_prefixes = exempt_ip_prefixes or []
        self._counters: Dict[Tuple[str, str, int], List[float]] = {}
        self._lock = threading.Lock()

    def is_exempt(self, ip: str) -> bool:
        """Return True if the given IP is exempt from rate limiting."""
        return any(ip.startswith(p) for p in self._exempt_prefixes)

    def _client_identifier(self, category: str) -> str:
        """Build a stable client identifier for the current request."""
        return request.remote_addr or "unknown"

    def allow(self, category: str, client: str, now: Optional[float] = None) -> bool:
        """Record a request and decide whether it is allowed."""
        if category not in self._limits:
            return True

        max_requests, window = self._limits[category]
        now = now if now is not None else time.time()
        bucket_id = int(now // window)
        key = (category, client, bucket_id)

        with self._lock:
            if key in self._counters:
                timestamps = self._counters[key]
                timestamps.append(now)
                self._counters[key] = timestamps
            else:
                self._counters[key] = [now]

            for stale_key in [
                k for k in self._counters
                if k[0] == category and k[2] < bucket_id - 1
            ]:
                del self._counters[stale_key]

            return len(self._counters[key]) <= max_requests

    def check(self) -> Optional[str]:
        """Run the rate limit check for the current request."""
        category = classify_request(request.path)
        if category is None:
            return None

        client = self._client_identifier(category)
        if self.is_exempt(client):
            return None

        if not self.allow(category, client):
            return category
        return None


_rate_limiter = RateLimiter(exempt_ip_prefixes=["127.0.0.1", "::1"])


def rate_limit_key() -> Optional[str]:
    """Compatibility alias returning the rate-limit category."""
    return _rate_limiter.check()


def before_request_rate_limit() -> Optional[str]:
    """Flask before_request hook for rate limiting sensitive endpoints."""
    category = _rate_limiter.check()
    if category is not None:
        return (
            jsonify({
                "success": False,
                "message": "Too many requests. Please try again later.",
                "status": 429,
                "code": "RATE_LIMITED",
            }),
            429,
        )
    return None


def register_rate_limits(app) -> None:
    """Register the rate limiting middleware for the Flask application."""
    if app.config.get("RATE_LIMIT_ENABLED", True):
        app.before_request(before_request_rate_limit)
