"""Public pages: home, concert listing/detail, artists, info pages."""
import math
import re
from datetime import date, timedelta

from flask import (Blueprint, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from db import execute, query, scalar

bp = Blueprint("public", __name__)

CONCERT_SELECT = """
SELECT c.*, a.name AS artist_name, a.image AS artist_image,
  (SELECT MIN(t.price) FROM tickets t WHERE t.concert_id=c.id AND t.status='available') AS min_price,
  (SELECT COUNT(*) FROM tickets t WHERE t.concert_id=c.id AND t.status='available') AS available,
  (SELECT COUNT(*) FROM tickets t WHERE t.concert_id=c.id) AS capacity,
  (SELECT ROUND(AVG(r.rating),1) FROM reviews r WHERE r.concert_id=c.id) AS rating
FROM concerts c JOIN artists a ON a.id = c.artist_id
"""
PUBLIC_STATUSES = "('on_sale','sold_out','cancelled','completed')"


def fav_ids():
    if not g.user:
        return set()
    return {r["concert_id"] for r in query("SELECT concert_id FROM favorites WHERE user_id=%s", (g.user["id"],))}


def filter_options():
    return {
        "genres": [r["genre"] for r in query("SELECT DISTINCT genre FROM concerts ORDER BY genre")],
        "cities": [r["city"] for r in query("SELECT DISTINCT city FROM concerts ORDER BY city")],
    }


@bp.route("/")
def home():
    upcoming = "c.status IN ('on_sale','sold_out') AND c.date >= CURDATE()"
    featured = query(CONCERT_SELECT + f" WHERE {upcoming} AND c.featured=1 ORDER BY c.date LIMIT 5")
    today = date.today()
    weekend_end = today + timedelta(days=(6 - today.weekday()) % 7)
    this_week = query(CONCERT_SELECT + f" WHERE {upcoming} AND c.date BETWEEN %s AND %s ORDER BY c.date LIMIT 4",
                      (today, max(weekend_end, today + timedelta(days=3))))
    soon = query(CONCERT_SELECT + f" WHERE {upcoming} ORDER BY c.date LIMIT 8")
    artists = query("SELECT a.*, COUNT(c.id) AS shows FROM artists a LEFT JOIN concerts c ON c.artist_id=a.id "
                    "AND c.date >= CURDATE() GROUP BY a.id ORDER BY shows DESC, a.name LIMIT 6")
    stats = {
        "concerts": scalar(f"SELECT COUNT(*) FROM concerts c WHERE {upcoming}"),
        "cities": scalar("SELECT COUNT(DISTINCT city) FROM concerts"),
        "fans": scalar("SELECT COUNT(*) FROM users WHERE role='customer'"),
    }
    return render_template("index.html", featured=featured, this_week=this_week, soon=soon,
                           artists=artists, stats=stats, favs=fav_ids(), **filter_options())


@bp.route("/concerts")
def concerts():
    q = request.args.get("q", "").strip()
    city = request.args.get("city", "")
    genre = request.args.get("genre", "")
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    when = request.args.get("when", "")
    sort = request.args.get("sort", "date")
    show_past = request.args.get("past") == "1"
    page = max(1, request.args.get("page", 1, type=int))

    where, args = [f"c.status IN {PUBLIC_STATUSES}"], []
    if not show_past:
        where.append("c.date >= CURDATE()")
    if q:
        where.append("(c.title LIKE %s OR a.name LIKE %s OR c.venue LIKE %s OR c.genre LIKE %s)")
        args += [f"%{q}%"] * 4
    if city:
        where.append("c.city = %s")
        args.append(city)
    if genre:
        where.append("c.genre = %s")
        args.append(genre)
    today = date.today()
    if when == "weekend":
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        if today.weekday() == 6:
            sat = today - timedelta(days=1)
        date_from, date_to = str(max(today, sat)), str(sat + timedelta(days=1))
    elif when == "week":
        date_from, date_to = str(today), str(today + timedelta(days=7))
    elif when == "month":
        date_from, date_to = str(today), str(today + timedelta(days=30))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_from or ""):
        where.append("c.date >= %s")
        args.append(date_from)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_to or ""):
        where.append("c.date <= %s")
        args.append(date_to)

    order = {
        "date": "c.date ASC, c.time ASC",
        "price_low": "min_price IS NULL, min_price ASC",
        "price_high": "min_price DESC",
        "popular": "(capacity - available) DESC",
        "name": "a.name ASC",
    }.get(sort, "c.date ASC")

    sql_where = " WHERE " + " AND ".join(where)
    total = scalar("SELECT COUNT(*) FROM concerts c JOIN artists a ON a.id=c.artist_id" + sql_where, args)
    per_page = 9
    pages = max(1, math.ceil(total / per_page))
    page = min(page, pages)
    rows = query(CONCERT_SELECT + sql_where + f" ORDER BY {order} LIMIT %s OFFSET %s",
                 args + [per_page, (page - 1) * per_page])
    params = {k: v for k, v in request.args.items() if k != "page"}
    return render_template("concerts.html", concerts=rows, total=total, page=page, pages=pages,
                           params=params, q=q, city=city, genre=genre, date_from=date_from if not when else "",
                           date_to=date_to if not when else "", when=when, sort=sort, show_past=show_past,
                           favs=fav_ids(), **filter_options())


@bp.route("/concerts/<int:concert_id>")
def concert_detail(concert_id):
    c = query(CONCERT_SELECT + " WHERE c.id=%s", (concert_id,), one=True)
    if not c or (c["status"] == "draft" and not (g.user and g.user["role"] == "admin")):
        abort(404)
    artist = query("SELECT * FROM artists WHERE id=%s", (c["artist_id"],), one=True)
    venue = query("SELECT * FROM venues WHERE id=%s", (c["venue_id"],), one=True) if c["venue_id"] else None
    tiers = query("SELECT type, MIN(price) AS price, SUM(status='available') AS available, COUNT(*) AS total "
                  "FROM tickets WHERE concert_id=%s GROUP BY type "
                  "ORDER BY FIELD(type,'VVIP','VIP','CAT 1','General Admission')", (concert_id,))
    reviews = query("SELECT r.*, u.name, EXISTS(SELECT 1 FROM orders o WHERE o.user_id=r.user_id AND "
                    "o.concert_id=r.concert_id AND o.payment_status='paid') AS verified "
                    "FROM reviews r JOIN users u ON u.id=r.user_id WHERE r.concert_id=%s "
                    "ORDER BY r.created_at DESC", (concert_id,))
    artist_reviews = []
    if not reviews:
        artist_reviews = query("SELECT r.*, u.name, c.title AS concert_title FROM reviews r "
                               "JOIN users u ON u.id=r.user_id JOIN concerts c ON c.id=r.concert_id "
                               "WHERE c.artist_id=%s ORDER BY r.created_at DESC LIMIT 4", (c["artist_id"],))
    my_review = None
    if g.user:
        my_review = query("SELECT * FROM reviews WHERE user_id=%s AND concert_id=%s",
                          (g.user["id"], concert_id), one=True)
    similar = query(CONCERT_SELECT + " WHERE c.id<>%s AND c.status='on_sale' AND c.date>=CURDATE() "
                    "AND (c.genre=%s OR c.city=%s) ORDER BY c.genre=%s DESC, c.date LIMIT 4",
                    (concert_id, c["genre"], c["city"], c["genre"]))
    return render_template("concert_detail.html", c=c, artist=artist, venue=venue, tiers=tiers,
                           reviews=reviews, artist_reviews=artist_reviews, my_review=my_review,
                           similar=similar, favs=fav_ids())


@bp.route("/concerts/<int:concert_id>/review", methods=["POST"])
def post_review(concert_id):
    if not g.user:
        flash("Log in to write a review.", "info")
        return redirect(url_for("auth.login", next=url_for("public.concert_detail", concert_id=concert_id)))
    rating = request.form.get("rating", type=int)
    comment = request.form.get("comment", "").strip()[:1000]
    if not rating or not 1 <= rating <= 5:
        flash("Please choose a rating from 1 to 5 stars.", "error")
    else:
        execute("INSERT INTO reviews (user_id, concert_id, rating, comment) VALUES (%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE rating=VALUES(rating), comment=VALUES(comment), created_at=NOW()",
                (g.user["id"], concert_id, rating, comment))
        flash("Thanks! Your review has been posted.", "success")
    return redirect(url_for("public.concert_detail", concert_id=concert_id) + "#reviews")


@bp.route("/concerts/<int:concert_id>/review/delete", methods=["POST"])
def delete_review(concert_id):
    if g.user:
        execute("DELETE FROM reviews WHERE user_id=%s AND concert_id=%s", (g.user["id"], concert_id))
        flash("Your review was removed.", "info")
    return redirect(url_for("public.concert_detail", concert_id=concert_id) + "#reviews")


@bp.route("/api/favorites/<int:concert_id>", methods=["POST"])
def toggle_favorite(concert_id):
    if not g.user:
        return jsonify(ok=False, error="Log in to save favourites.", login=url_for("auth.login")), 401
    exists = scalar("SELECT COUNT(*) FROM favorites WHERE user_id=%s AND concert_id=%s",
                    (g.user["id"], concert_id))
    if exists:
        execute("DELETE FROM favorites WHERE user_id=%s AND concert_id=%s", (g.user["id"], concert_id))
    else:
        execute("INSERT INTO favorites (user_id, concert_id) VALUES (%s,%s)", (g.user["id"], concert_id))
    return jsonify(ok=True, favorite=not exists)


@bp.route("/artists/<int:artist_id>")
def artist(artist_id):
    a = query("SELECT * FROM artists WHERE id=%s", (artist_id,), one=True)
    if not a:
        abort(404)
    shows = query(CONCERT_SELECT + f" WHERE c.artist_id=%s AND c.status IN {PUBLIC_STATUSES} "
                  "ORDER BY c.date >= CURDATE() DESC, c.date", (artist_id,))
    return render_template("artist.html", a=a, shows=shows, favs=fav_ids())


@bp.route("/about")
def about():
    return render_template("about.html")


@bp.route("/faq")
def faq():
    return render_template("faq.html")


@bp.route("/refund-policy")
def refund():
    return render_template("refund.html")


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = {"name": "", "email": "", "subject": "", "message": ""}
    if g.user:
        form.update(name=g.user["name"], email=g.user["email"])
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        errors = []
        if len(form["name"]) < 2:
            errors.append("Please enter your name.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", form["email"]):
            errors.append("Please enter a valid email address.")
        if len(form["subject"]) < 3:
            errors.append("Please add a subject.")
        if len(form["message"]) < 10:
            errors.append("Your message should be at least 10 characters.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            execute("INSERT INTO contact_messages (name,email,subject,message) VALUES (%s,%s,%s,%s)",
                    (form["name"], form["email"], form["subject"][:200], form["message"][:5000]))
            flash("Thanks for getting in touch! Our team usually replies within one business day.", "success")
            return redirect(url_for("public.contact"))
    return render_template("contact.html", form=form)
