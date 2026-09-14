from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, render_template, request

from src.web.blueprints import api_bp, views_bp

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Application factory for Hermes diagnostics and configuration web console."""
    app = Flask(
        __name__,
        template_folder=TEMPLATES_DIR,
    )

    app.config.from_mapping(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "hermes-insecure-secret-key"),
        JSON_SORT_KEYS=False,
    )

    if test_config:
        app.config.update(test_config)

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    _register_security_headers(app)
    _register_error_handlers(app)

    return app


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Auth-Token"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def handle_not_found(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found"}), 404
        return render_template("index.html"), 404

    @app.errorhandler(400)
    def handle_bad_request(error):
        return jsonify({"error": str(error) or "Bad request"}), 400

    @app.errorhandler(500)
    def handle_server_error(error):
        return jsonify({"error": "Internal server error"}), 500
