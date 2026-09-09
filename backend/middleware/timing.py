"""Request timing middleware."""

import time
from flask import Request, g


def start_timer() -> None:
    """Start request timer."""
    g.start_time = time.time()


def get_request_duration() -> float:
    """Get elapsed request duration."""
    if hasattr(g, "start_time"):
        return time.time() - g.start_time
    return 0.0
