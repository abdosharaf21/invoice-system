"""Static modular serving (Phase 8 production single-box deployments)."""

from backend.modules.static.routes import create_static_blueprint

__all__ = ["create_static_blueprint"]