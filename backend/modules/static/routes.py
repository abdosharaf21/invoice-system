"""Static SPA serving for single-box production deployments.

The Phase 8 production topology prefers Nginx serving the frontend and
proxying ``/api/`` to Gunicorn. This blueprint enables a simpler single-host
deployment where Flask also serves the built SPA when ``SERVE_STATIC`` is on.

The SPA uses a hash router, so only the entry document and its asset tree
need to be served — no server-side route fallback is required.
``send_from_directory`` guarantees path-traversal safety.
"""

import logging

from flask import Blueprint, send_from_directory

logger = logging.getLogger(__name__)


def create_static_blueprint(dist_dir: str, url_prefix: str = "") -> Blueprint:
    """Create a blueprint serving the built SPA from ``dist_dir``.

    Args:
        dist_dir: Absolute path to the directory containing ``index.html``
            and an ``assets/`` subtree.
        url_prefix: Optional URL prefix for the served routes.

    Returns:
        A Blueprint serving the entry document and ``/assets/<path>`` files.
    """
    static_bp = Blueprint("static", __name__, url_prefix=url_prefix)

    @static_bp.get("/")
    @static_bp.get("/index.html")
    def index():
        return send_from_directory(dist_dir, "index.html")

    @static_bp.get("/assets/<path:filename>")
    def assets(filename):
        return send_from_directory(f"{dist_dir}/assets", filename)

    return static_bp