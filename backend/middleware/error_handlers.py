"""Global error handlers for Flask application."""

import logging
import mysql.connector
from flask import Flask, jsonify, request

from backend.middleware.exceptions import (
    AppException,
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    ValidationException,
    DatabaseException,
    ServiceUnavailableException
)

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    """Register global error handlers for the Flask application."""

    @app.errorhandler(BadRequestException)
    def handle_bad_request(error):
        logger.warning("Bad request: %s %s - %s", request.method, request.path, error.message)
        return jsonify(error.to_dict()), 400

    @app.errorhandler(UnauthorizedException)
    def handle_unauthorized(error):
        logger.warning("Unauthorized: %s %s - %s", request.method, request.path, error.message)
        return jsonify(error.to_dict()), 401

    @app.errorhandler(ForbiddenException)
    def handle_forbidden(error):
        logger.warning("Forbidden: %s %s - %s", request.method, request.path, error.message)
        return jsonify(error.to_dict()), 403

    @app.errorhandler(NotFoundException)
    def handle_not_found(error):
        logger.warning("Not found: %s %s - %s", request.method, request.path, error.message)
        return jsonify(error.to_dict()), 404

    @app.errorhandler(ConflictException)
    def handle_conflict(error):
        logger.warning("Conflict: %s %s - %s", request.method, request.path, error.message)
        return jsonify(error.to_dict()), 409

    @app.errorhandler(ValidationException)
    def handle_validation(error):
        logger.warning("Validation error: %s %s - %s", request.method, request.path, error.message)
        return jsonify(error.to_dict()), 422

    @app.errorhandler(DatabaseException)
    def handle_database(error):
        logger.error("Database error: %s %s - %s", request.method, request.path, error.message, exc_info=True)
        return jsonify(error.to_dict()), 500

    @app.errorhandler(mysql.connector.Error)
    def handle_mysql_error(error):
        logger.error("MySQL error: %s %s - %s", request.method, request.path, str(error), exc_info=True)
        return jsonify({
            "success": False,
            "message": "A database error occurred",
            "status": 500,
            "code": "DATABASE_ERROR",
        }), 500

    @app.errorhandler(ServiceUnavailableException)
    def handle_service_unavailable(error):
        logger.error("Service unavailable: %s %s - %s", request.method, request.path, error.message)
        return jsonify(error.to_dict()), 503

    @app.errorhandler(ValueError)
    def handle_value_error(error):
        logger.warning("Value error: %s %s - %s", request.method, request.path, str(error))
        return jsonify({
            "success": False,
            "message": str(error),
            "status": 400,
            "code": "BAD_REQUEST",
        }), 400

    @app.errorhandler(KeyError)
    def handle_key_error(error):
        logger.warning("Key error: %s %s - Missing key: %s", request.method, request.path, str(error))
        return jsonify({
            "success": False,
            "message": f"Missing required field: {str(error)}",
            "status": 400,
            "code": "MISSING_FIELD",
        }), 400

    @app.errorhandler(PermissionError)
    def handle_permission_error(error):
        logger.warning("Permission error: %s %s - %s", request.method, request.path, str(error))
        return jsonify({
            "success": False,
            "message": "Permission denied",
            "status": 403,
            "code": "FORBIDDEN",
        }), 403

    @app.errorhandler(400)
    def handle_400(error):
        return jsonify({
            "success": False,
            "message": "Bad request",
            "status": 400,
            "code": "BAD_REQUEST",
        }), 400

    @app.errorhandler(401)
    def handle_401(error):
        return jsonify({
            "success": False,
            "message": "Unauthorized",
            "status": 401,
            "code": "UNAUTHORIZED",
        }), 401

    @app.errorhandler(403)
    def handle_403(error):
        return jsonify({
            "success": False,
            "message": "Access denied",
            "status": 403,
            "code": "FORBIDDEN",
        }), 403

    @app.errorhandler(404)
    def handle_404(error):
        return jsonify({
            "success": False,
            "message": "Resource not found",
            "status": 404,
            "code": "NOT_FOUND",
        }), 404

    @app.errorhandler(405)
    def handle_405(error):
        return jsonify({
            "success": False,
            "message": "Method not allowed",
            "status": 405,
            "code": "METHOD_NOT_ALLOWED",
        }), 405

    @app.errorhandler(409)
    def handle_409(error):
        return jsonify({
            "success": False,
            "message": "Resource conflict",
            "status": 409,
            "code": "CONFLICT",
        }), 409

    @app.errorhandler(422)
    def handle_422(error):
        return jsonify({
            "success": False,
            "message": "Unprocessable entity",
            "status": 422,
            "code": "VALIDATION_ERROR",
        }), 422

    @app.errorhandler(429)
    def handle_429(error):
        return jsonify({
            "success": False,
            "message": "Too many requests",
            "status": 429,
            "code": "RATE_LIMITED",
        }), 429

    @app.errorhandler(500)
    def handle_500(error):
        logger.error("Internal server error: %s %s - %s", request.method, request.path, str(error), exc_info=True)
        return jsonify({
            "success": False,
            "message": "Internal server error",
            "status": 500,
            "code": "INTERNAL_ERROR",
        }), 500

    @app.errorhandler(502)
    def handle_502(error):
        return jsonify({
            "success": False,
            "message": "Bad gateway",
            "status": 502,
            "code": "BAD_GATEWAY",
        }), 502

    @app.errorhandler(503)
    def handle_503(error):
        return jsonify({
            "success": False,
            "message": "Service unavailable",
            "status": 503,
            "code": "SERVICE_UNAVAILABLE",
        }), 503

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error):
        logger.error("Unexpected error: %s %s - %s", request.method, request.path, str(error), exc_info=True)
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred",
            "status": 500,
            "code": "INTERNAL_ERROR",
        }), 500
