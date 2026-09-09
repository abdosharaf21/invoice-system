"""WSGI entry point for web deployments.

Run with gunicorn from the repository root::

    backend/.venv/bin/gunicorn --bind 0.0.0.0:5001 backend.wsgi:application
"""

import logging

from backend.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

application = create_app()

app = application
