"""BRRR Scout — Flask application factory."""
import datetime, logging, logging.handlers, os, pathlib

_LOG_DIR = pathlib.Path(__file__).parent.parent / "data"
_LOG_FILE = _LOG_DIR / "logs.txt"


def _setup_logging():
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    stream_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    # Quiet down noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


_setup_logging()
log = logging.getLogger("brrr_scout")


def create_app():
    from flask import Flask

    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "brrr-scout-local")

    log.info("Flask app starting — env: %s", os.environ.get("FLASK_ENV", "production"))

    @app.template_filter("gbp")
    def gbp(v):
        return f"£{v:,.0f}" if v is not None else "—"

    @app.template_filter("ts")
    def ts(v):
        return datetime.datetime.fromtimestamp(v).strftime("%d %b %Y") if v else "—"

    from . import routes
    routes.init_app(app)

    log.info("Flask app ready — routes registered")
    return app
