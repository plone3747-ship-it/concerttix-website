"""ConcertTix - online concert ticket booking (demo / portfolio project).

Run with:   python app.py      then open http://127.0.0.1:5000
"""
import json

from flask import Flask, g, render_template

import db
from config import Config
from utils import (csrf_protect, csrf_token, days_until, fmt_date, fmt_time,
                   image_url, label, load_user, money)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    db.init_app(app)

    from routes.public import bp as public_bp
    from routes.auth import bp as auth_bp
    from routes.booking import bp as booking_bp
    from routes.account import bp as account_bp
    from routes.assistant import bp as assistant_bp
    from admin.routes import bp as admin_bp

    for bp in (public_bp, auth_bp, booking_bp, account_bp, assistant_bp, admin_bp):
        app.register_blueprint(bp)

    @app.before_request
    def _before():
        load_user()
        return csrf_protect()

    @app.context_processor
    def _globals():
        currencies = {k: v for k, v in app.config["CURRENCIES"].items()}
        return {
            "csrf_token": csrf_token,
            "currencies_json": json.dumps(currencies),
            "currency_codes": list(currencies.keys()),
            "fee_rate": app.config["SERVICE_FEE_RATE"],
            "current_user": g.get("user"),
        }

    app.jinja_env.filters.update(
        time=fmt_time, date=fmt_date, money=money, image=image_url,
        label=label, days_until=days_until,
    )

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403, title="Admins only",
                               message="You don't have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, title="Page not found",
                               message="The page you were looking for has left the building."), 404

    @app.errorhandler(413)
    def too_big(_e):
        return render_template("error.html", code=413, title="File too large",
                               message="Images must be 5 MB or smaller."), 413

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
