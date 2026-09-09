"""Flask application entry point."""

import os
import sys
import atexit
import logging
from datetime import timedelta

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cwd = os.getcwd()

if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from flask import Flask, jsonify, request, g
from flask_jwt_extended import JWTManager

from backend.config import get_config
from backend.database import Database

from backend.modules.auth.routes import auth_bp, init_auth_service
from backend.modules.auth.repository import AuthRepository
from backend.modules.auth.service import AuthService

from backend.modules.users.routes import users_bp, init_user_service
from backend.modules.users.repository import UserRepository
from backend.modules.users.service import UserService
from backend.modules.users.model import User

from backend.middleware import (
    register_error_handlers,
    register_security_headers,
    register_cors,
    start_timer,
    get_request_duration,
    log_request,
    log_response,
    load_user_context,
    get_request_id,
    REQUEST_ID_HEADER,
)
from backend.middleware.rate_limit import register_rate_limits

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

jwt_blocklist = set()


def create_app(config: dict = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config: Optional configuration dictionary to override defaults.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)

    config_class = get_config()
    config_class.validate()

    log_level = getattr(logging, config_class.LOG_LEVEL.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)
    logger.info("Log level set to %s", config_class.LOG_LEVEL.upper())

    app.config["SECRET_KEY"] = config_class.SECRET_KEY
    app.config["JWT_SECRET_KEY"] = config_class.JWT_SECRET_KEY
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(seconds=config_class.JWT_ACCESS_TOKEN_EXPIRES)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(seconds=config_class.JWT_REFRESH_TOKEN_EXPIRES)
    app.config["JWT_TOKEN_LOCATION"] = config_class.JWT_TOKEN_LOCATION
    app.config["JWT_HEADER_NAME"] = config_class.JWT_HEADER_NAME
    app.config["JWT_HEADER_TYPE"] = config_class.JWT_HEADER_TYPE
    app.config["MAX_CONTENT_LENGTH"] = config_class.MAX_CONTENT_LENGTH
    app.config["DEBUG"] = config_class.DEBUG
    app.config["SECURITY_HEADERS_ENABLED"] = config_class.SECURITY_HEADERS_ENABLED
    app.config["CSP_ENABLED"] = config_class.CSP_ENABLED
    app.config["CSP_POLICY"] = config_class.CSP_POLICY
    app.config["HSTS_ENABLED"] = config_class.HSTS_ENABLED
    app.config["CORS_ORIGINS"] = config_class.CORS_ORIGINS
    app.config["CORS_EXPAND_LAN"] = config_class.CORS_EXPAND_LAN
    app.config["RATE_LIMIT_ENABLED"] = config_class.RATE_LIMIT_ENABLED

    if config:
        app.config.update(config)

    jwt = JWTManager(app)

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload["jti"]
        return jti in jwt_blocklist

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "success": False,
            "message": "Token has expired",
            "status": 401,
            "code": "TOKEN_EXPIRED"
        }), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error_string):
        return jsonify({
            "success": False,
            "message": "Invalid token",
            "status": 401,
            "code": "INVALID_TOKEN"
        }), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error_string):
        return jsonify({
            "success": False,
            "message": "Authorization token is required",
            "status": 401,
            "code": "TOKEN_REQUIRED"
        }), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "success": False,
            "message": "Token has been revoked",
            "status": 401,
            "code": "TOKEN_REVOKED"
        }), 401

    register_error_handlers(app)
    register_security_headers(app)
    register_rate_limits(app)
    register_cors(
        app,
        allowed_origins=app.config.get("CORS_ORIGINS"),
        expand_lan=app.config.get("CORS_EXPAND_LAN", True),
    )

    @app.before_request
    def before_request():
        start_timer()
        log_request(request)
        load_user_context()

    @app.after_request
    def after_request(response):
        duration = get_request_duration()
        response.headers["X-Request-Duration"] = f"{duration:.4f}s"
        response.headers[REQUEST_ID_HEADER] = get_request_id()
        log_response(response, g.get("start_time", 0))
        return response

    @app.teardown_appcontext
    def teardown_context(exception):
        pass

    database = Database()

    user_repo = UserRepository(database)
    user_service = UserService(user_repo, jwt_blocklist)
    init_user_service(user_service, jwt_blocklist)

    auth_repo = AuthRepository(database)
    auth_service = AuthService(auth_repo, user_repo, jwt_blocklist)
    init_auth_service(auth_service)

    atexit.register(database.close_all)

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)

    @app.get("/api/health")
    def health_check():
        """Health check endpoint."""
        return jsonify({"success": True, "message": "Invoice System API is running"})

    return app


if __name__ == "__main__":
    config_class = get_config()

    application = create_app()
    application.run(
        debug=config_class.DEBUG,
        host=config_class.SERVER_HOST,
        port=config_class.SERVER_PORT,
    )
