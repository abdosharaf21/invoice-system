"""CORS middleware for Flask application."""

import socket
from typing import List, Optional

from flask import Response, request


def _get_lan_ip() -> str:
    """Detect the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


_LAN_IP = _get_lan_ip()
DEFAULT_ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
DEFAULT_ALLOWED_HEADERS = ["Content-Type", "Authorization", "X-Requested-With"]
DEFAULT_EXPOSE_HEADERS = ["Content-Length", "X-Request-Id"]
DEFAULT_MAX_AGE = 3600


def _expand_origins(origins: List[str]) -> List[str]:
    """Expand origin list with LAN IP variants."""
    result = list(origins)
    if _LAN_IP:
        for origin in origins:
            if "localhost" in origin:
                result.append(origin.replace("localhost", _LAN_IP))
    return result


def create_cors_middleware(
    allowed_origins: Optional[List[str]] = None,
    allowed_methods: Optional[List[str]] = None,
    allowed_headers: Optional[List[str]] = None,
    expose_headers: Optional[List[str]] = None,
    max_age: int = DEFAULT_MAX_AGE,
    allow_credentials: bool = True,
    expand_lan: bool = True,
) -> callable:
    """Create CORS middleware with configurable options."""
    if allowed_origins is None:
        allowed_origins = ["http://localhost:5173"]

    if allowed_methods is None:
        allowed_methods = DEFAULT_ALLOWED_METHODS

    if allowed_headers is None:
        allowed_headers = DEFAULT_ALLOWED_HEADERS

    if expose_headers is None:
        expose_headers = DEFAULT_EXPOSE_HEADERS

    if expand_lan:
        allowed_origins = _expand_origins(allowed_origins)

    def cors_after_request(response: Response) -> Response:
        origin = request.headers.get("Origin")

        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            if allow_credentials:
                response.headers["Access-Control-Allow-Credentials"] = "true"
        elif "*" in allowed_origins and not allow_credentials:
            response.headers["Access-Control-Allow-Origin"] = "*"

        response.headers["Access-Control-Allow-Methods"] = ", ".join(allowed_methods)
        response.headers["Access-Control-Allow-Headers"] = ", ".join(allowed_headers)
        response.headers["Access-Control-Expose-Headers"] = ", ".join(expose_headers)
        response.headers["Access-Control-Max-Age"] = str(max_age)

        return response

    return cors_after_request


def handle_preflight_request(response: Response) -> Response:
    """Handle CORS preflight (OPTIONS) requests."""
    if request.method == "OPTIONS":
        response.headers["Access-Control-Allow-Methods"] = ", ".join(DEFAULT_ALLOWED_METHODS)
        response.headers["Access-Control-Allow-Headers"] = ", ".join(DEFAULT_ALLOWED_HEADERS)
        response.headers["Access-Control-Max-Age"] = str(DEFAULT_MAX_AGE)
        response.headers["Vary"] = "Origin"

    return response


def register_cors(
    app,
    allowed_origins: Optional[List[str]] = None,
    expand_lan: bool = True,
) -> None:
    """Register CORS middleware for the Flask application."""
    cors_handler = create_cors_middleware(
        allowed_origins=allowed_origins,
        expand_lan=expand_lan,
    )
    app.after_request(cors_handler)
    app.after_request(handle_preflight_request)
