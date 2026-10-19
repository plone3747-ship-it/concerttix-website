"""Shared helpers: login checks, CSRF protection, uploads, formatting."""
import os
import secrets
import uuid
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (abort, current_app, flash, g, jsonify, redirect, request,
                   session, url_for)
from werkzeug.utils import secure_filename

from db import query


# ----------------------------------------------------------------- users
def load_user():
    g.user = None
    uid = session.get("user_id")
    if uid:
        g.user = query("SELECT id,name,email,phone,role,created_at FROM users WHERE id=%s", (uid,), one=True)
        if g.user is None:
            session.clear()


def wants_json():
    return request.is_json or request.path.startswith("/api/")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if wants_json():
                return jsonify(ok=False, error="Please log in first.", login=url_for("auth.login")), 401
            flash("Please log in to continue.", "info")
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path))
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def safe_next(target):
    """Only allow redirects within this site."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


# ------------------------------------------------------------------ CSRF
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        if not sent or sent != session.get("_csrf"):
            if wants_json():
                return jsonify(ok=False, error="Your session expired. Please refresh the page."), 400
            flash("Your session expired. Please try again.", "error")
            return redirect(request.referrer or url_for("public.home"))


# --------------------------------------------------------------- uploads
def save_upload(file_storage, subfolder):
    """Save an uploaded image, return its path relative to /static, or None."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in current_app.config["ALLOWED_IMAGE_EXT"]:
        flash("Image must be PNG, JPG, WEBP, GIF or SVG.", "error")
        return None
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}-{secure_filename(file_storage.filename)}"
    file_storage.save(os.path.join(folder, name))
    return f"uploads/{subfolder}/{name}"


def image_url(path):
    if not path:
        return url_for("static", filename="img/placeholder.svg")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return url_for("static", filename=path)


# ------------------------------------------------------------ formatting
def fmt_time(value):
    if value is None:
        return ""
    if isinstance(value, timedelta):
        secs = int(value.total_seconds())
        h, m = secs // 3600, (secs % 3600) // 60
    else:
        h, m = value.hour, value.minute
    suffix = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12}:{m:02d} {suffix}"


def time_input(value):
    """TIME -> 'HH:MM' for <input type=time>."""
    if isinstance(value, timedelta):
        secs = int(value.total_seconds())
        return f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}"
    return value.strftime("%H:%M") if value else ""


def fmt_date(value, fmt="%a, %d %b %Y"):
    if not value:
        return ""
    if isinstance(value, str):
        value = datetime.strptime(value[:10], "%Y-%m-%d").date()
    return value.strftime(fmt)


def money(value):
    return f"S${float(value or 0):,.2f}"


def days_until(value):
    if isinstance(value, datetime):
        value = value.date()
    return (value - date.today()).days


STATUS_LABELS = {
    "on_sale": "On sale", "sold_out": "Sold out", "cancelled": "Cancelled",
    "completed": "Completed", "draft": "Draft", "paid": "Paid", "refunded": "Refunded",
    "pending": "Pending", "failed": "Failed", "open": "Open", "approved": "Approved",
    "rejected": "Rejected", "card": "Card", "apple_pay": "Apple Pay",
    "google_pay": "Google Pay", "paypal": "PayPal", "invalid_ticket": "Invalid ticket",
    "not_delivered": "Ticket not delivered", "event_cancelled": "Event cancelled", "other": "Other",
}


def label(value):
    return STATUS_LABELS.get(value, str(value).replace("_", " ").title())
