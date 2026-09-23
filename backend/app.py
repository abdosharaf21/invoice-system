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
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager

from backend.config import get_config
from backend.database import Database

from backend.modules.auth.routes import auth_bp, init_auth_service
from backend.modules.auth.repository import AuthRepository
from backend.modules.auth.service import AuthService

from backend.modules.users.routes import users_bp, init_user_service
from backend.modules.users.repository import UserRepository
from backend.modules.users.service import UserService

from backend.modules.audit_trail.routes import (
    audit_trail_bp,
    init_audit_trail_service,
)
from backend.modules.audit_trail.repository import AuditTrailRepository
from backend.modules.audit_trail.service import (
    AuditTrailService,
    set_audit_enabled,
)

from backend.modules.companies.repository import CompanyRepository
from backend.modules.companies.service import CompanyService
from backend.modules.companies.routes import (
    company_settings_bp,
    init_company_settings_service,
)

from backend.modules.settings.routes import settings_bp, init_settings_service
from backend.modules.settings.repository import ApplicationSettingRepository
from backend.modules.settings.service import ApplicationSettingService

from backend.modules.imports.routes import imports_bp, init_import_service
from backend.modules.imports.repository import ImportBatchRepository
from backend.modules.imports.service import ImportService
from backend.modules.invoices.repository import InvoiceRepository

from backend.modules.reconciliation.routes import (
    reconciliation_bp,
    init_reconciliation_service,
)
from backend.modules.reconciliation.repository import ReconciliationRepository
from backend.modules.reconciliation.service import ReconciliationService
from backend.modules.tax_authority.repository import TaxInvoiceRepository

from backend.modules.email.routes import email_bp, init_email_service
from backend.modules.email.repository import EmailDeliveryRepository
from backend.modules.email.service import EmailService

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
    new_request_id,
    REQUEST_ID_HEADER,
)
from backend.middleware.logger import configure_logging, DEFAULT_LOG_LEVEL
from backend.middleware.rate_limit import register_rate_limits

configure_logging(DEFAULT_LOG_LEVEL)
logger = logging.getLogger(__name__)

jwt_blocklist = set()


def register_api_v1_aliases(app: Flask) -> None:
    """Expose every ``/api/<...>`` route under an equivalent ``/api/v1/<...>`` rule.

    V1 (``/api/v1``) is the documented, stable namespace. The unversioned
    ``/api/...`` routes keep working as compatibility aliases so existing
    clients and the frontend continue to function unchanged. Both prefixes
    resolve to the very same view functions; no business logic is duplicated.

    Args:
        app: The configured Flask application.
    """
    for rule in list(app.url_map.iter_rules()):
        path = rule.rule
        if not path.startswith("/api/"):
            continue
        if path.startswith("/api/v1/"):
            continue
        v1_path = "/api/v1" + path[len("/api"):]
        app.add_url_rule(
            v1_path,
            endpoint=f"{rule.endpoint}__v1",
            view_func=app.view_functions[rule.endpoint],
            methods=list(rule.methods),
            defaults=rule.defaults,
            host=rule.host,
            strict_slashes=rule.strict_slashes,
        )


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
    configure_logging(log_level)
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
    app.config["RATE_LIMIT_EXEMPT_IPS"] = config_class.RATE_LIMIT_EXEMPT_IPS
    app.config["AUDIT_LOG_ENABLED"] = config_class.AUDIT_LOG_ENABLED
    app.config["SERVE_STATIC"] = config_class.SERVE_STATIC
    app.config["FRONTEND_DIST"] = config_class.FRONTEND_DIST
    app.config["EMAIL_ENABLED"] = config_class.EMAIL_ENABLED
    app.config["EMAIL_PROVIDER"] = config_class.EMAIL_PROVIDER
    app.config["EMAIL_HOST"] = config_class.EMAIL_HOST
    app.config["EMAIL_PORT"] = config_class.EMAIL_PORT
    app.config["EMAIL_USERNAME"] = config_class.EMAIL_USERNAME
    app.config["EMAIL_PASSWORD"] = config_class.EMAIL_PASSWORD
    app.config["EMAIL_FROM"] = config_class.EMAIL_FROM
    app.config["EMAIL_USE_TLS"] = config_class.EMAIL_USE_TLS
    app.config["EMAIL_USE_SSL"] = config_class.EMAIL_USE_SSL

    if config:
        app.config.update(config)

    database = Database()
    app.extensions["database"] = database

    jwt = JWTManager(app)

    auth_repo = AuthRepository(database)

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload["jti"]
        if jti in jwt_blocklist:
            return True
        return auth_repo.is_blocklisted(jti)

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
    register_cors(
        app,
        allowed_origins=app.config.get("CORS_ORIGINS"),
        expand_lan=app.config.get("CORS_EXPAND_LAN", True),
    )

    @app.before_request
    def before_request():
        start_timer()
        new_request_id(request)
        load_user_context()
        log_request(request)

    @app.after_request
    def after_request(response):
        duration = get_request_duration()
        response.headers["X-Request-Duration"] = f"{duration:.4f}s"
        response.headers[REQUEST_ID_HEADER] = get_request_id()
        log_response(response, duration)
        return response

    @app.teardown_appcontext
    def teardown_context(exception):
        pass

    # Rate limiting is registered last so the timing, correlation and user
    # context hooks above always run first. Rate-limited requests therefore
    # still carry a request id, an accurate duration and a rejection log.
    register_rate_limits(app)

    set_audit_enabled(app.config.get("AUDIT_LOG_ENABLED", True))
    audit_repo = AuditTrailRepository(database)
    audit_service = AuditTrailService(audit_repo)
    init_audit_trail_service(audit_service)

    user_repo = UserRepository(database)
    user_service = UserService(
        user_repo,
        jwt_blocklist,
        company_repository=CompanyRepository(database),
        auth_repository=auth_repo,
    )
    init_user_service(user_service, jwt_blocklist)

    company_repo = CompanyRepository(database)
    company_service = CompanyService(company_repo)
    init_company_settings_service(company_service, user_service)

    app_settings_repo = ApplicationSettingRepository(database)
    app_settings_service = ApplicationSettingService(app_settings_repo)
    init_settings_service(app_settings_service, user_service)

    auth_service = AuthService(auth_repo, user_repo, jwt_blocklist)
    init_auth_service(auth_service)

    batch_repo = ImportBatchRepository(database)
    invoice_repo = InvoiceRepository(database)
    import_service = ImportService(batch_repo, invoice_repo, user_repo)
    init_import_service(import_service)

    tax_repo = TaxInvoiceRepository(database)
    recon_repo = ReconciliationRepository(database)
    delivery_repo = EmailDeliveryRepository(database)

    email_service = EmailService(
        config_mapping=app.config,
        company_repo=company_repo,
        delivery_repo=delivery_repo,
        recon_repo=recon_repo,
    )
    init_email_service(email_service)

    reconciliation_service = ReconciliationService(
        recon_repo, invoice_repo, tax_repo, user_repo,
        email_service=email_service,
    )
    init_reconciliation_service(reconciliation_service)

    for label, recover in (
        ("import batches", import_service.recover_interrupted),
        ("reconciliation runs", reconciliation_service.recover_interrupted),
    ):
        try:
            recovered = recover()
            if recovered:
                logger.info("Recovered %s to failed on startup", label)
        except Exception:
            logger.exception("Failed to recover interrupted %s on startup", label)

    atexit.register(database.close_all)

    app.register_blueprint(auth_bp)
    app.register_blueprint(audit_trail_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(reconciliation_bp)
    app.register_blueprint(company_settings_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(email_bp)

    @app.get("/api/health")
    def health_check():
        """Liveness health check endpoint."""
        return jsonify({
            "success": True,
            "status": "ok",
            "message": "Invoice System API is running",
        })

    @app.get("/api/health/ready")
    def health_ready():
        """Readiness check: reports application and database availability.

        Returns 200 only when the database connection pool is operational,
        and 503 otherwise so orchestration tiers can shift traffic or
        restart the worker. No infrastructure details are exposed.
        """
        database = app.extensions.get("database")
        healthy = True
        if database is not None:
            try:
                healthy = bool(database.is_healthy)
            except Exception:
                healthy = False
        if not healthy:
            app.logger.warning("Readiness check failed: database unavailable")
            return jsonify({
                "success": False,
                "status": "error",
                "message": "Database unavailable",
            }), 503
        return jsonify({
            "success": True,
            "status": "ok",
            "message": "Ready",
            "data": {"database": "ok"},
        }), 200

    if app.config.get("SERVE_STATIC"):
        from backend.modules.static.routes import create_static_blueprint
        app.register_blueprint(create_static_blueprint(app.config.get("FRONTEND_DIST")))

    # Versioning: register the stable /api/v1 namespace as aliases of the
    # existing /api routes. Kept last so every API rule, health endpoint,
    # blueprint and middleware hook is already registered when aliased.
    register_api_v1_aliases(app)

    logger.info(
        "Invoice System API started (env=%s debug=%s log_level=%s)",
        config_class.FLASK_ENV,
        app.config.get("DEBUG"),
        config_class.LOG_LEVEL,
    )

    return app


if __name__ == "__main__":
    config_class = get_config()

    if config_class.FLASK_ENV == "production":
        raise SystemExit(
            "Refusing to start the Flask development server in production. "
            "Run the application with Gunicorn instead: "
            "gunicorn --bind 0.0.0.0:8000 backend.wsgi:application"
        )

    application = create_app()
    application.run(
        debug=config_class.DEBUG,
        host=config_class.SERVER_HOST,
        port=config_class.SERVER_PORT,
    )
