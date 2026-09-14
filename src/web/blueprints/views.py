from __future__ import annotations

from flask import Blueprint, render_template

views_bp = Blueprint("views", __name__)

PAGE_ROUTES = (
    "/",
    "/index",
    "/scale",
    "/anpr",
    "/cloud",
    "/wifi",
    "/telemetry",
    "/errors",
    "/config",
)


for route in PAGE_ROUTES:
    views_bp.add_url_rule(
        route,
        endpoint=f"page_{route.strip('/') or 'home'}",
        view_func=lambda: render_template("index.html"),
    )
