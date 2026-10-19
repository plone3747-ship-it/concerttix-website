"""Login, sign-up and logout."""
import re

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import execute, query
from utils import safe_next

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _login(user):
    keep = session.get("currency")
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True
    if keep:
        session["currency"] = keep


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("public.home"))
    nxt = safe_next(request.values.get("next"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = query("SELECT * FROM users WHERE email=%s", (email,), one=True)
        if user and check_password_hash(user["password"], password):
            _login(user)
            flash(f"Welcome back, {user['name'].split()[0]}!", "success")
            if nxt:
                return redirect(nxt)
            return redirect(url_for("admin.dashboard") if user["role"] == "admin" else url_for("public.home"))
        flash("Incorrect email or password.", "error")
    return render_template("auth/login.html", next=nxt, email=email)


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user:
        return redirect(url_for("public.home"))
    nxt = safe_next(request.values.get("next"))
    form = {"name": "", "email": "", "phone": ""}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        form["email"] = form["email"].lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        errors = []
        if len(form["name"]) < 2:
            errors.append("Please enter your full name.")
        if not EMAIL_RE.fullmatch(form["email"]):
            errors.append("Please enter a valid email address.")
        if not re.fullmatch(r"\+?[\d\s\-()]{7,20}", form["phone"]):
            errors.append("Please enter a valid phone number.")
        if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            errors.append("Password needs at least 8 characters, including a letter and a number.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if not request.form.get("terms"):
            errors.append("Please accept the terms and refund policy.")
        if not errors and query("SELECT id FROM users WHERE email=%s", (form["email"],), one=True):
            errors.append("An account with this email already exists. Try logging in.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            uid = execute("INSERT INTO users (name,email,phone,password,role) VALUES (%s,%s,%s,%s,'customer')",
                          (form["name"], form["email"], form["phone"], generate_password_hash(password)))
            _login({"id": uid})
            flash("Your account is ready. Enjoy the show!", "success")
            return redirect(nxt or url_for("public.home"))
    return render_template("auth/signup.html", form=form, next=nxt)


@bp.route("/logout", methods=["POST", "GET"])
def logout():
    keep = session.get("currency")
    session.clear()
    if keep:
        session["currency"] = keep
    flash("You have been logged out.", "info")
    return redirect(url_for("public.home"))
