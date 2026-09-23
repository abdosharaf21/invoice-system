"""WSGI entry-point import smoke test (Phase 14 gap G8).

Ensures the production entry point assembles an importable Flask
``application`` without touching a real database or server.
"""

import importlib

from flask import Flask


def test_wsgi_app_imports_cleanly():
    module = importlib.import_module("backend.wsgi")
    application = module.application
    assert isinstance(application, Flask)


def test_wsgi_aliases_application():
    module = importlib.import_module("backend.wsgi")
    assert module.app is module.application