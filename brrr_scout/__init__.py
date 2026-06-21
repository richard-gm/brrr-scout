"""BRRR Scout — Flask application factory."""
import datetime
from flask import Flask


def create_app():
    app = Flask(__name__)
    app.secret_key = "brrr-scout-local"

    @app.template_filter("gbp")
    def gbp(v):
        return f"£{v:,.0f}" if v is not None else "—"

    @app.template_filter("ts")
    def ts(v):
        return datetime.datetime.fromtimestamp(v).strftime("%d %b %Y") if v else "—"

    from . import routes
    routes.init_app(app)

    return app
