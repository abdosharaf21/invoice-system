"""Tests for the optional SPA static-serving blueprint (Phase 8)."""

from flask import Flask

from backend.modules.static.routes import create_static_blueprint


def _make_app(dist_dir):
    app = Flask(__name__)
    app.register_blueprint(create_static_blueprint(dist_dir))
    return app


def test_static_serves_index_and_assets(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>app</body></html>")
    (dist / "assets" / "app.js").write_text("console.log('app')")

    client = _make_app(str(dist)).test_client()

    root = client.get("/")
    assert root.status_code == 200
    assert "app" in root.get_data(as_text=True)

    direct = client.get("/index.html")
    assert direct.status_code == 200

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert asset.mimetype == "text/javascript"
    assert "console.log" in asset.get_data(as_text=True)


def test_static_blocks_path_traversal(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")
    (tmp_path / "secret.txt").write_text("top-secret")

    client = _make_app(str(dist)).test_client()
    response = client.get("/assets/../secret.txt")
    assert response.status_code in (403, 404)


def test_static_has_no_catch_all(tmp_path):
    """No catch-all: unknown routes must 404, never shadow API routes."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>")

    client = _make_app(str(dist)).test_client()
    assert client.get("/missing-page").status_code == 404
    assert client.get("/assets/does-not-exist.js").status_code == 404


def test_static_serving_is_opt_in(client):
    """Default app (SERVE_STATIC off) must not serve the SPA root."""
    assert client.get("/").status_code == 404


def test_static_serving_survives_api_routing(static_serving_app):
    """With SERVE_STATIC on, SPA root and API routes coexist."""
    client = static_serving_app.test_client()
    assert client.get("/").status_code == 200
    assert "SPA" in client.get("/").get_data(as_text=True)
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/api/health").status_code == 200