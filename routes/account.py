"""Customer area: bookings, tickets, favourites, profile, guarantee claims."""
import re

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import execute, query
from routes.public import CONCERT_SELECT
from utils import login_required

bp = Blueprint("account", __name__)

ORDER_SELECT = ("SELECT o.*, c.title, c.date, c.time, c.venue, c.city, c.image, c.status AS concert_status, "
                "a.name AS artist_name, (SELECT GROUP_CONCAT(t.seat ORDER BY t.id SEPARATOR ', ') FROM tickets t "
                "WHERE t.order_id=o.id) AS seats, (SELECT status FROM guarantee_claims gc WHERE gc.order_id=o.id "
                "ORDER BY gc.id DESC LIMIT 1) AS claim_status FROM orders o JOIN concerts c ON c.id=o.concert_id "
                "JOIN artists a ON a.id=c.artist_id ")


@bp.route("/my-bookings")
@login_required
def bookings():
    tab = request.args.get("tab", "upcoming")
    where = "o.user_id=%s"
    if tab == "upcoming":
        where += " AND c.date >= CURDATE() AND o.payment_status='paid'"
    elif tab == "past":
        where += " AND (c.date < CURDATE() OR o.payment_status<>'paid')"
    orders = query(ORDER_SELECT + f"WHERE {where} ORDER BY " +
                   ("c.date ASC" if tab == "upcoming" else "o.order_date DESC"), (g.user["id"],))
    totals = query("SELECT COUNT(*) AS orders, COALESCE(SUM(tickets),0) AS tickets, COALESCE(SUM(total),0) AS spent "
                   "FROM orders WHERE user_id=%s AND payment_status='paid'", (g.user["id"],), one=True)
    return render_template("account/bookings.html", orders=orders, tab=tab, totals=totals)


@bp.route("/my-tickets")
@login_required
def tickets():
    rows = query("SELECT t.*, o.order_ref, c.title, c.date, c.time, c.venue, c.city, c.image, c.age_limit, "
                 "a.name AS artist_name FROM tickets t JOIN orders o ON o.id=t.order_id "
                 "JOIN concerts c ON c.id=t.concert_id JOIN artists a ON a.id=c.artist_id "
                 "WHERE o.user_id=%s AND o.payment_status='paid' AND t.status='sold' AND c.date >= CURDATE() "
                 "AND c.status <> 'cancelled' ORDER BY c.date, c.time, t.id", (g.user["id"],))
    return render_template("account/tickets.html", tickets=rows)


@bp.route("/favorites")
@login_required
def favorites():
    rows = query(CONCERT_SELECT + " JOIN favorites f ON f.concert_id=c.id WHERE f.user_id=%s "
                 "ORDER BY c.date >= CURDATE() DESC, c.date", (g.user["id"],))
    return render_template("account/favorites.html", concerts=rows, favs={c["id"] for c in rows})


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "details":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            if len(name) < 2 or not re.fullmatch(r"\+?[\d\s\-()]{7,20}", phone):
                flash("Please enter a valid name and phone number.", "error")
            else:
                execute("UPDATE users SET name=%s, phone=%s WHERE id=%s", (name, phone, g.user["id"]))
                flash("Profile updated.", "success")
        elif action == "password":
            user = query("SELECT password FROM users WHERE id=%s", (g.user["id"],), one=True)
            new = request.form.get("new_password", "")
            if not check_password_hash(user["password"], request.form.get("current_password", "")):
                flash("Your current password is incorrect.", "error")
            elif len(new) < 8 or not re.search(r"[A-Za-z]", new) or not re.search(r"\d", new):
                flash("New password needs 8+ characters with a letter and a number.", "error")
            elif new != request.form.get("confirm_password"):
                flash("New passwords do not match.", "error")
            else:
                execute("UPDATE users SET password=%s WHERE id=%s", (generate_password_hash(new), g.user["id"]))
                flash("Password changed.", "success")
        return redirect(url_for("account.profile"))
    return render_template("account/profile.html")


@bp.route("/bookings/<ref>/claim", methods=["POST"])
@login_required
def claim(ref):
    o = query("SELECT * FROM orders WHERE order_ref=%s AND user_id=%s", (ref, g.user["id"]), one=True)
    if not o:
        abort(404)
    reason = request.form.get("reason")
    details = request.form.get("details", "").strip()[:2000]
    if reason not in ("invalid_ticket", "not_delivered", "event_cancelled", "other"):
        flash("Please choose a reason for your claim.", "error")
    elif query("SELECT id FROM guarantee_claims WHERE order_id=%s AND status='open'", (o["id"],), one=True):
        flash("You already have an open claim for this booking.", "info")
    else:
        execute("INSERT INTO guarantee_claims (order_id,user_id,reason,details) VALUES (%s,%s,%s,%s)",
                (o["id"], g.user["id"], reason, details))
        flash("Claim submitted. Our team will review it within 2 business days.", "success")
    return redirect(url_for("booking.confirmation", ref=ref))
