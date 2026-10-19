"""Admin dashboard at /admin."""
import csv
import io
import math
import os
from datetime import date, datetime, timedelta

from flask import (Blueprint, Response, abort, flash, g, jsonify,
                   redirect, render_template, request, url_for)

from db import execute, query, scalar, transaction
from services import seating
from services.posters import artist_svg, poster_svg, save_svg
from utils import admin_required, save_upload, time_input

bp = Blueprint("admin", __name__, url_prefix="/admin")
STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
PER_PAGE = 20


@bp.before_request
@admin_required
def _guard():
    pass


@bp.context_processor
def _admin_ctx():
    return {
        "open_claims": scalar("SELECT COUNT(*) FROM guarantee_claims WHERE status='open'"),
        "unread_messages": scalar("SELECT COUNT(*) FROM contact_messages WHERE is_read=0"),
        "time_input": time_input,
    }


def paginate(count_sql, args):
    total = scalar(count_sql, args)
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(max(1, request.args.get("page", 1, type=int)), pages)
    return total, page, pages, (page - 1) * PER_PAGE


def refund_order(cur, order_id):
    """Refund an order: mark refunded and put its seats back on sale."""
    cur.execute("UPDATE orders SET payment_status='refunded' WHERE id=%s", (order_id,))
    cur.execute("UPDATE tickets SET status='available', order_id=NULL, qr_token=NULL, checked_in_at=NULL "
                "WHERE order_id=%s", (order_id,))
    cur.execute("UPDATE concerts c JOIN orders o ON o.concert_id=c.id SET c.status='on_sale' "
                "WHERE o.id=%s AND c.status='sold_out'", (order_id,))


# ================================================================ dashboard
@bp.route("/")
def dashboard():
    paid = "payment_status='paid'"
    stats = {
        "sales": scalar(f"SELECT COUNT(*) FROM orders WHERE {paid}"),
        "tickets": scalar(f"SELECT COALESCE(SUM(tickets),0) FROM orders WHERE {paid}"),
        "users": scalar("SELECT COUNT(*) FROM users WHERE role='customer'"),
        "upcoming": scalar("SELECT COUNT(*) FROM concerts WHERE date>=CURDATE() AND status IN ('on_sale','sold_out')"),
        "revenue": float(scalar(f"SELECT COALESCE(SUM(total),0) FROM orders WHERE {paid}")),
        "fees": float(scalar(f"SELECT COALESCE(SUM(service_fee),0) FROM orders WHERE {paid}")),
    }
    last30 = f"{paid} AND order_date >= CURDATE() - INTERVAL 29 DAY"
    stats["revenue_30"] = float(scalar(f"SELECT COALESCE(SUM(total),0) FROM orders WHERE {last30}"))
    stats["tickets_30"] = int(scalar(f"SELECT COALESCE(SUM(tickets),0) FROM orders WHERE {last30}"))

    daily = {r["d"]: r for r in query(
        f"SELECT DATE(order_date) d, SUM(tickets) t, SUM(total) r FROM orders WHERE {last30} GROUP BY d")}
    days = [date.today() - timedelta(days=i) for i in range(29, -1, -1)]
    sales_chart = {"labels": [d.strftime("%d %b") for d in days],
                   "tickets": [int(daily[d]["t"]) if d in daily else 0 for d in days],
                   "revenue": [float(daily[d]["r"]) if d in daily else 0 for d in days]}

    months = []
    first = date.today().replace(day=1)
    for i in range(5, -1, -1):
        y, m = first.year, first.month - i
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))
    monthly = {(r["y"], r["m"]): float(r["r"]) for r in query(
        f"SELECT YEAR(order_date) y, MONTH(order_date) m, SUM(total) r FROM orders WHERE {paid} "
        "AND order_date >= %s GROUP BY y, m", (date(months[0][0], months[0][1], 1),))}
    revenue_chart = {"labels": [date(y, m, 1).strftime("%b %Y") for y, m in months],
                     "values": [monthly.get(k, 0) for k in months]}

    popular = query(f"SELECT c.title, a.name artist, SUM(o.tickets) t, SUM(o.total) r FROM orders o "
                    f"JOIN concerts c ON c.id=o.concert_id JOIN artists a ON a.id=c.artist_id "
                    f"WHERE o.{paid} GROUP BY c.id ORDER BY t DESC LIMIT 6")
    by_type = query(f"SELECT t.type, COUNT(*) n FROM tickets t JOIN orders o ON o.id=t.order_id "
                    f"WHERE o.{paid} GROUP BY t.type ORDER BY FIELD(t.type,'VVIP','VIP','CAT 1','General Admission')")
    recent = query("SELECT o.*, c.title FROM orders o JOIN concerts c ON c.id=o.concert_id "
                   "ORDER BY o.order_date DESC LIMIT 8")
    upcoming = query("SELECT c.id, c.title, c.date, c.venue, a.name artist, "
                     "SUM(t.status='sold') sold, COUNT(t.id) cap FROM concerts c JOIN artists a ON a.id=c.artist_id "
                     "LEFT JOIN tickets t ON t.concert_id=c.id WHERE c.date>=CURDATE() AND c.status IN "
                     "('on_sale','sold_out') GROUP BY c.id ORDER BY c.date LIMIT 6")
    charts = {
        "sales": sales_chart, "revenue": revenue_chart,
        "popular": {"labels": [p["artist"] for p in popular], "titles": [p["title"] for p in popular],
                    "values": [int(p["t"]) for p in popular]},
        "types": {"labels": [t["type"] for t in by_type], "values": [int(t["n"]) for t in by_type]},
    }
    return render_template("admin/dashboard.html", stats=stats, charts=charts, recent=recent, upcoming=upcoming)


# ================================================================ concerts
TIERS = seating.TICKET_TYPES


@bp.route("/concerts")
def concerts():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    where, args = ["1=1"], []
    if q:
        where.append("(c.title LIKE %s OR a.name LIKE %s OR c.venue LIKE %s)")
        args += [f"%{q}%"] * 3
    if status:
        where.append("c.status=%s")
        args.append(status)
    w = " AND ".join(where)
    total, page, pages, offset = paginate(
        f"SELECT COUNT(*) FROM concerts c JOIN artists a ON a.id=c.artist_id WHERE {w}", args)
    rows = query(f"SELECT c.*, a.name artist, "
                 f"(SELECT COUNT(*) FROM tickets t WHERE t.concert_id=c.id AND t.status='sold') sold, "
                 f"(SELECT COUNT(*) FROM tickets t WHERE t.concert_id=c.id) cap, "
                 f"(SELECT COALESCE(SUM(total),0) FROM orders o WHERE o.concert_id=c.id AND o.payment_status='paid') revenue "
                 f"FROM concerts c JOIN artists a ON a.id=c.artist_id WHERE {w} "
                 f"ORDER BY c.date DESC LIMIT {PER_PAGE} OFFSET {offset}", args)
    return render_template("admin/concerts.html", rows=rows, q=q, status=status, total=total, page=page, pages=pages)


def concert_form_data():
    return {"artists": query("SELECT id, name, genre FROM artists ORDER BY name"),
            "venues": query("SELECT * FROM venues ORDER BY city, name")}


def read_concert_form():
    f = request.form
    data = {k: f.get(k, "").strip() for k in
            ("title", "date", "time", "genre", "age_limit", "description", "status", "artist_id", "venue_id")}
    data["featured"] = 1 if f.get("featured") else 0
    prices = {}
    errors = []
    for t in TIERS:
        try:
            prices[t] = round(float(f.get("price_" + t.replace(" ", "_"), "")), 2)
            if prices[t] < 0:
                raise ValueError
        except ValueError:
            errors.append(f"Enter a valid price for {t}.")
    if len(data["title"]) < 2:
        errors.append("Title is required.")
    try:
        datetime.strptime(data["date"], "%Y-%m-%d")
        datetime.strptime(data["time"], "%H:%M")
    except ValueError:
        errors.append("Enter a valid date and time.")
    if not data["artist_id"].isdigit():
        errors.append("Choose an artist.")
    venue = None
    if data["venue_id"].isdigit():
        venue = query("SELECT * FROM venues WHERE id=%s", (data["venue_id"],), one=True)
    if not venue:
        errors.append("Choose a venue.")
    if data["status"] not in ("on_sale", "sold_out", "cancelled", "completed", "draft"):
        data["status"] = "draft"
    if not data["genre"] and data["artist_id"].isdigit():
        data["genre"] = scalar("SELECT genre FROM artists WHERE id=%s", (data["artist_id"],), "") or "Pop"
    data["age_limit"] = data["age_limit"] or "All ages"
    return data, prices, venue, errors


def make_poster(concert_id, data, venue):
    artist = query("SELECT name FROM artists WHERE id=%s", (data["artist_id"],), one=True)
    d = datetime.strptime(data["date"], "%Y-%m-%d")
    return save_svg(STATIC, "posters", f"concert-{concert_id}.svg",
                    poster_svg(data["title"], artist["name"], d.strftime("%a %d %b %Y").upper(),
                               venue["name"], concert_id))


@bp.route("/concerts/new", methods=["GET", "POST"])
def concert_new():
    c = {"status": "on_sale", "age_limit": "All ages", "time": "20:00"}
    prices = dict(seating.DEFAULT_PRICES)
    if request.method == "POST":
        data, prices, venue, errors = read_concert_form()
        if errors:
            for e in errors:
                flash(e, "error")
            c = data
        else:
            image = save_upload(request.files.get("image"), "concerts")
            with transaction() as cur:
                cur.execute("INSERT INTO concerts (artist_id,venue_id,title,image,date,time,venue,city,genre,age_limit,"
                            "description,status,featured) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (data["artist_id"], venue["id"], data["title"], image, data["date"], data["time"],
                             venue["name"], venue["city"], data["genre"], data["age_limit"], data["description"],
                             data["status"], data["featured"]))
                cid = cur.lastrowid
                seating.create_inventory(cur, cid, prices)
                if not image:
                    cur.execute("UPDATE concerts SET image=%s WHERE id=%s", (make_poster(cid, data, venue), cid))
            flash(f"Concert \"{data['title']}\" created with {len(seating.build_inventory_rows(cid, prices))} tickets.", "success")
            return redirect(url_for("admin.concerts"))
    return render_template("admin/concert_form.html", c=c, prices=prices, tiers=TIERS, **concert_form_data())


@bp.route("/concerts/<int:cid>/edit", methods=["GET", "POST"])
def concert_edit(cid):
    c = query("SELECT * FROM concerts WHERE id=%s", (cid,), one=True)
    if not c:
        abort(404)
    prices = seating.type_prices(cid)
    if request.method == "POST":
        data, new_prices, venue, errors = read_concert_form()
        if errors:
            for e in errors:
                flash(e, "error")
            c.update(data)
            prices = new_prices
        else:
            image = save_upload(request.files.get("image"), "concerts")
            with transaction() as cur:
                cur.execute("UPDATE concerts SET artist_id=%s, venue_id=%s, title=%s, date=%s, time=%s, venue=%s, "
                            "city=%s, genre=%s, age_limit=%s, description=%s, status=%s, featured=%s WHERE id=%s",
                            (data["artist_id"], venue["id"], data["title"], data["date"], data["time"], venue["name"],
                             venue["city"], data["genre"], data["age_limit"], data["description"], data["status"],
                             data["featured"], cid))
                for t, p in new_prices.items():   # new price applies to unsold tickets only
                    cur.execute("UPDATE tickets SET price=%s WHERE concert_id=%s AND type=%s AND status<>'sold'",
                                (p, cid, t))
                if image:
                    cur.execute("UPDATE concerts SET image=%s WHERE id=%s", (image, cid))
                elif request.form.get("regenerate") or not c["image"] or c["image"].startswith("img/posters/"):
                    cur.execute("UPDATE concerts SET image=%s WHERE id=%s", (make_poster(cid, data, venue), cid))
            flash("Concert updated.", "success")
            return redirect(url_for("admin.concerts"))
    return render_template("admin/concert_form.html", c=c, prices=prices, tiers=TIERS, **concert_form_data())


@bp.route("/concerts/<int:cid>/delete", methods=["POST"])
def concert_delete(cid):
    if scalar("SELECT COUNT(*) FROM orders WHERE concert_id=%s", (cid,)):
        flash("This concert has orders, so it can't be deleted. Set its status to Cancelled instead "
              "(customers can then claim refunds).", "error")
    else:
        execute("DELETE FROM concerts WHERE id=%s", (cid,))
        flash("Concert deleted.", "success")
    return redirect(url_for("admin.concerts"))


# ================================================================ artists
@bp.route("/artists")
def artists():
    q = request.args.get("q", "").strip()
    rows = query("SELECT a.*, COUNT(c.id) shows FROM artists a LEFT JOIN concerts c ON c.artist_id=a.id "
                 "WHERE a.name LIKE %s OR a.genre LIKE %s GROUP BY a.id ORDER BY a.name", (f"%{q}%", f"%{q}%"))
    return render_template("admin/artists.html", rows=rows, q=q)


@bp.route("/artists/new", methods=["GET", "POST"])
@bp.route("/artists/<int:aid>/edit", methods=["GET", "POST"])
def artist_form(aid=None):
    a = query("SELECT * FROM artists WHERE id=%s", (aid,), one=True) if aid else {}
    if aid and not a:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        genre = request.form.get("genre", "").strip()
        desc = request.form.get("description", "").strip()
        if len(name) < 2 or not genre:
            flash("Name and genre are required.", "error")
            a = {**a, "name": name, "genre": genre, "description": desc}
        else:
            image = save_upload(request.files.get("image"), "artists")
            if aid:
                execute("UPDATE artists SET name=%s, genre=%s, description=%s WHERE id=%s", (name, genre, desc, aid))
            else:
                aid = execute("INSERT INTO artists (name, genre, description) VALUES (%s,%s,%s)", (name, genre, desc))
            if image:
                execute("UPDATE artists SET image=%s WHERE id=%s", (image, aid))
            elif not a.get("image") or a["image"].startswith("img/artists/"):
                execute("UPDATE artists SET image=%s WHERE id=%s",
                        (save_svg(STATIC, "artists", f"artist-{aid}.svg", artist_svg(name, aid)), aid))
            flash("Artist saved.", "success")
            return redirect(url_for("admin.artists"))
    return render_template("admin/artist_form.html", a=a)


@bp.route("/artists/<int:aid>/delete", methods=["POST"])
def artist_delete(aid):
    if scalar("SELECT COUNT(*) FROM concerts WHERE artist_id=%s", (aid,)):
        flash("This artist has concerts. Delete or reassign those concerts first.", "error")
    else:
        execute("DELETE FROM artists WHERE id=%s", (aid,))
        flash("Artist deleted.", "success")
    return redirect(url_for("admin.artists"))


# ================================================================ venues
@bp.route("/venues")
def venues():
    rows = query("SELECT v.*, COUNT(c.id) shows FROM venues v LEFT JOIN concerts c ON c.venue_id=v.id "
                 "GROUP BY v.id ORDER BY v.city, v.name")
    return render_template("admin/venues.html", rows=rows)


@bp.route("/venues/new", methods=["GET", "POST"])
@bp.route("/venues/<int:vid>/edit", methods=["GET", "POST"])
def venue_form(vid=None):
    v = query("SELECT * FROM venues WHERE id=%s", (vid,), one=True) if vid else {}
    if vid and not v:
        abort(404)
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in ("name", "address", "city", "capacity")}
        if len(f["name"]) < 2 or len(f["address"]) < 4 or not f["city"] or not f["capacity"].isdigit():
            flash("Please fill in name, address, city and a numeric capacity.", "error")
            v = {**v, **f}
        else:
            if vid:
                execute("UPDATE venues SET name=%s, address=%s, city=%s, capacity=%s WHERE id=%s",
                        (f["name"], f["address"], f["city"], int(f["capacity"]), vid))
                execute("UPDATE concerts SET venue=%s, city=%s WHERE venue_id=%s", (f["name"], f["city"], vid))
            else:
                execute("INSERT INTO venues (name,address,city,capacity) VALUES (%s,%s,%s,%s)",
                        (f["name"], f["address"], f["city"], int(f["capacity"])))
            flash("Venue saved.", "success")
            return redirect(url_for("admin.venues"))
    return render_template("admin/venue_form.html", v=v)


@bp.route("/venues/<int:vid>/delete", methods=["POST"])
def venue_delete(vid):
    if scalar("SELECT COUNT(*) FROM concerts WHERE venue_id=%s AND date>=CURDATE()", (vid,)):
        flash("This venue has upcoming concerts. Move them to another venue first.", "error")
    else:
        execute("DELETE FROM venues WHERE id=%s", (vid,))
        flash("Venue deleted.", "success")
    return redirect(url_for("admin.venues"))


# ================================================================ orders
def order_filters():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    concert = request.args.get("concert", "", type=str)
    where, args = ["1=1"], []
    if q:
        where.append("(o.order_ref LIKE %s OR o.customer_name LIKE %s OR o.customer_email LIKE %s)")
        args += [f"%{q}%"] * 3
    if status:
        where.append("o.payment_status=%s")
        args.append(status)
    if concert.isdigit():
        where.append("o.concert_id=%s")
        args.append(int(concert))
    return " AND ".join(where), args, q, status, concert


@bp.route("/orders")
def orders():
    w, args, q, status, concert = order_filters()
    total, page, pages, offset = paginate(f"SELECT COUNT(*) FROM orders o WHERE {w}", args)
    rows = query(f"SELECT o.*, c.title FROM orders o JOIN concerts c ON c.id=o.concert_id WHERE {w} "
                 f"ORDER BY o.order_date DESC LIMIT {PER_PAGE} OFFSET {offset}", args)
    sums = query(f"SELECT COALESCE(SUM(o.total),0) revenue, COALESCE(SUM(o.tickets),0) tickets FROM orders o "
                 f"WHERE {w} AND o.payment_status='paid'", args, one=True)
    concerts = query("SELECT id, title, date FROM concerts ORDER BY date DESC")
    return render_template("admin/orders.html", rows=rows, q=q, status=status, concert=concert, concerts=concerts,
                           total=total, page=page, pages=pages, sums=sums)


@bp.route("/orders.csv")
def orders_csv():
    w, args, *_ = order_filters()
    rows = query(f"SELECT o.order_ref, o.order_date, o.customer_name, o.customer_email, o.customer_phone, c.title, "
                 f"o.tickets, o.subtotal, o.service_fee, o.total, o.currency, o.payment_method, o.payment_status "
                 f"FROM orders o JOIN concerts c ON c.id=o.concert_id WHERE {w} ORDER BY o.order_date DESC", args)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Order", "Date", "Customer", "Email", "Phone", "Concert", "Tickets", "Subtotal (SGD)",
                     "Service fee (SGD)", "Total (SGD)", "Display currency", "Method", "Status"])
    for r in rows:
        writer.writerow(list(r.values()))
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=concerttix-orders-{date.today()}.csv"})


@bp.route("/orders/<int:oid>")
def order_detail(oid):
    o = query("SELECT o.*, c.title, c.date, c.time, c.venue, c.city, u.email AS account_email FROM orders o "
              "JOIN concerts c ON c.id=o.concert_id JOIN users u ON u.id=o.user_id WHERE o.id=%s", (oid,), one=True)
    if not o:
        abort(404)
    tickets = query("SELECT * FROM tickets WHERE order_id=%s ORDER BY id", (oid,))
    claims = query("SELECT * FROM guarantee_claims WHERE order_id=%s ORDER BY id DESC", (oid,))
    return render_template("admin/order_detail.html", o=o, tickets=tickets, claims=claims)


@bp.route("/orders/<int:oid>/refund", methods=["POST"])
def order_refund(oid):
    o = query("SELECT * FROM orders WHERE id=%s", (oid,), one=True)
    if not o or o["payment_status"] != "paid":
        flash("Only paid orders can be refunded.", "error")
    else:
        with transaction() as cur:
            refund_order(cur, oid)
            cur.execute("UPDATE guarantee_claims SET status='approved', admin_note='Refunded by admin' "
                        "WHERE order_id=%s AND status='open'", (oid,))
        flash(f"Order {o['order_ref']} refunded (demo) and its seats are back on sale.", "success")
    return redirect(url_for("admin.order_detail", oid=oid))


# ================================================================ customers
@bp.route("/customers")
def customers():
    q = request.args.get("q", "").strip()
    role = request.args.get("role", "")
    where, args = ["(u.name LIKE %s OR u.email LIKE %s OR u.phone LIKE %s)"], [f"%{q}%"] * 3
    if role in ("customer", "admin"):
        where.append("u.role=%s")
        args.append(role)
    w = " AND ".join(where)
    total, page, pages, offset = paginate(f"SELECT COUNT(*) FROM users u WHERE {w}", args)
    rows = query(f"SELECT u.id, u.name, u.email, u.phone, u.role, u.created_at, "
                 f"COUNT(o.id) orders, COALESCE(SUM(o.total),0) spent, MAX(o.order_date) last_order "
                 f"FROM users u LEFT JOIN orders o ON o.user_id=u.id AND o.payment_status='paid' WHERE {w} "
                 f"GROUP BY u.id ORDER BY u.created_at DESC LIMIT {PER_PAGE} OFFSET {offset}", args)
    return render_template("admin/customers.html", rows=rows, q=q, role=role, total=total, page=page, pages=pages)


@bp.route("/customers/<int:uid>")
def customer_detail(uid):
    u = query("SELECT * FROM users WHERE id=%s", (uid,), one=True)
    if not u:
        abort(404)
    orders = query("SELECT o.*, c.title, c.date FROM orders o JOIN concerts c ON c.id=o.concert_id "
                   "WHERE o.user_id=%s ORDER BY o.order_date DESC", (uid,))
    reviews = query("SELECT r.*, c.title FROM reviews r JOIN concerts c ON c.id=r.concert_id WHERE r.user_id=%s "
                    "ORDER BY r.created_at DESC", (uid,))
    favs = query("SELECT c.id, c.title FROM favorites f JOIN concerts c ON c.id=f.concert_id WHERE f.user_id=%s", (uid,))
    return render_template("admin/customer_detail.html", u=u, orders=orders, reviews=reviews, favs=favs)


@bp.route("/customers/<int:uid>/role", methods=["POST"])
def customer_role(uid):
    if uid == g.user["id"]:
        flash("You can't change your own role.", "error")
    else:
        role = "admin" if request.form.get("role") == "admin" else "customer"
        execute("UPDATE users SET role=%s WHERE id=%s", (role, uid))
        flash(f"Role changed to {role}.", "success")
    return redirect(url_for("admin.customer_detail", uid=uid))


# ================================================================ inventory
@bp.route("/inventory")
def inventory_index():
    rows = query("SELECT c.id, c.title, c.date, c.status, a.name artist, "
                 "SUM(t.status='available') available, SUM(t.status='held') held, SUM(t.status='sold') sold, "
                 "SUM(t.status='blocked') blocked, COUNT(t.id) total FROM concerts c "
                 "JOIN artists a ON a.id=c.artist_id LEFT JOIN tickets t ON t.concert_id=c.id "
                 "GROUP BY c.id ORDER BY c.date < CURDATE(), c.date")
    return render_template("admin/inventory_index.html", rows=rows)


@bp.route("/inventory/<int:cid>")
def inventory(cid):
    seating.release_expired()
    c = query("SELECT c.*, a.name artist FROM concerts c JOIN artists a ON a.id=c.artist_id WHERE c.id=%s",
              (cid,), one=True)
    if not c:
        abort(404)
    tiers = query("SELECT type, MIN(price) price, MAX(price) max_price, COUNT(*) total, "
                  "SUM(status='available') available, SUM(status='held') held, SUM(status='sold') sold, "
                  "SUM(status='blocked') blocked FROM tickets WHERE concert_id=%s GROUP BY type "
                  "ORDER BY FIELD(type,'VVIP','VIP','CAT 1','General Admission')", (cid,))
    seats = query("SELECT id, seat, seat_row, seat_number, type, status FROM tickets WHERE concert_id=%s "
                  "AND type<>'General Admission' ORDER BY id", (cid,))
    rows = {}
    for s in seats:
        rows.setdefault(s["seat_row"], []).append(s)
    return render_template("admin/inventory.html", c=c, tiers=tiers, rows=rows, layout=seating.LAYOUT)


@bp.route("/inventory/<int:cid>/price", methods=["POST"])
def inventory_price(cid):
    ttype = request.form.get("type")
    try:
        price = round(float(request.form.get("price", "")), 2)
        assert price >= 0 and ttype in TIERS
    except (ValueError, AssertionError):
        flash("Enter a valid price.", "error")
        return redirect(url_for("admin.inventory", cid=cid))
    execute("UPDATE tickets SET price=%s WHERE concert_id=%s AND type=%s AND status<>'sold'", (price, cid, ttype))
    flash(f"{ttype} price set to S${price:,.2f} for all unsold tickets.", "success")
    return redirect(url_for("admin.inventory", cid=cid))


@bp.route("/inventory/<int:cid>/ga", methods=["POST"])
def inventory_ga(cid):
    action = request.form.get("action")
    qty = request.form.get("qty", 0, type=int)
    if qty <= 0 or qty > 1000:
        flash("Enter a quantity between 1 and 1000.", "error")
        return redirect(url_for("admin.inventory", cid=cid))
    with transaction() as cur:
        if action == "add":
            cur.execute("SELECT COALESCE(MAX(seat_number),0) n, COALESCE(MIN(price),88) p FROM tickets "
                        "WHERE concert_id=%s AND type='General Admission'", (cid,))
            r = cur.fetchone()
            cur.executemany(seating.INSERT_TICKET_SQL, [
                (cid, "General Admission", r["p"], f"GA-{n:03d}", None, n)
                for n in range(int(r["n"]) + 1, int(r["n"]) + qty + 1)])
            msg = f"Added {qty} General Admission spots."
        else:
            src, dst = ("available", "blocked") if action == "block" else ("blocked", "available")
            cur.execute(f"UPDATE tickets SET status=%s WHERE concert_id=%s AND type='General Admission' "
                        f"AND status=%s ORDER BY seat_number {'DESC' if action == 'block' else 'ASC'} LIMIT %s",
                        (dst, cid, src, qty))
            msg = f"{cur.rowcount} General Admission spots {'blocked' if action == 'block' else 'released'}."
    flash(msg, "success")
    return redirect(url_for("admin.inventory", cid=cid))


@bp.route("/api/inventory/<int:cid>/toggle", methods=["POST"])
def inventory_toggle(cid):
    ids = [int(i) for i in (request.get_json(silent=True) or {}).get("ids", []) if str(i).isdigit()]
    action = (request.get_json(silent=True) or {}).get("action")
    if not ids or action not in ("block", "release"):
        return jsonify(ok=False, error="Nothing selected."), 400
    ph = ",".join(["%s"] * len(ids))
    src, dst = ("available", "blocked") if action == "block" else ("blocked", "available")
    with transaction() as cur:
        cur.execute(f"UPDATE tickets SET status=%s WHERE concert_id=%s AND status=%s AND id IN ({ph})",
                    [dst, cid, src, *ids])
        changed = cur.rowcount
    return jsonify(ok=True, changed=changed, new_status=dst)


# ================================================================ check-in
@bp.route("/checkin")
def checkin():
    concerts = query("SELECT id, title, date FROM concerts WHERE status IN ('on_sale','sold_out','completed') "
                     "ORDER BY ABS(DATEDIFF(date, CURDATE())), date LIMIT 30")
    cid = request.args.get("concert", type=int) or (concerts[0]["id"] if concerts else None)
    stats, recent = None, []
    if cid:
        stats = query("SELECT COUNT(*) sold, SUM(checked_in_at IS NOT NULL) checked FROM tickets "
                      "WHERE concert_id=%s AND status='sold'", (cid,), one=True)
        recent = query("SELECT t.seat, t.type, t.checked_in_at, o.customer_name FROM tickets t JOIN orders o "
                       "ON o.id=t.order_id WHERE t.concert_id=%s AND t.checked_in_at IS NOT NULL "
                       "ORDER BY t.checked_in_at DESC LIMIT 12", (cid,))
    return render_template("admin/checkin.html", concerts=concerts, cid=cid, stats=stats, recent=recent)


@bp.route("/api/checkin", methods=["POST"])
def checkin_api():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip().upper()
    cid = data.get("concert_id")
    if not code:
        return jsonify(ok=False, result="invalid", message="Enter or scan a ticket code.")
    with transaction() as cur:
        cur.execute("SELECT t.*, o.customer_name, o.order_ref, o.payment_status, c.title FROM tickets t "
                    "JOIN orders o ON o.id=t.order_id JOIN concerts c ON c.id=t.concert_id "
                    "WHERE t.qr_token=%s FOR UPDATE", (code,))
        t = cur.fetchone()
        if not t or t["status"] != "sold" or t["payment_status"] != "paid":
            return jsonify(ok=False, result="invalid", message="Ticket not found or no longer valid.")
        info = {"seat": t["seat"], "type": t["type"], "name": t["customer_name"],
                "order": t["order_ref"], "concert": t["title"]}
        if cid and int(cid) != t["concert_id"]:
            return jsonify(ok=False, result="wrong", message=f"This ticket is for {t['title']}.", ticket=info)
        if t["checked_in_at"]:
            return jsonify(ok=False, result="used",
                           message=f"Already checked in at {t['checked_in_at']:%H:%M, %d %b}.", ticket=info)
        cur.execute("UPDATE tickets SET checked_in_at=NOW() WHERE id=%s", (t["id"],))
    return jsonify(ok=True, result="ok", message="Valid ticket - welcome in!", ticket=info)


# ================================================================ claims & messages
@bp.route("/claims")
def claims():
    status = request.args.get("status", "open")
    rows = query("SELECT gc.*, o.order_ref, o.total, o.payment_status, o.id order_id, u.name, u.email, c.title, "
                 "c.status concert_status FROM guarantee_claims gc JOIN orders o ON o.id=gc.order_id "
                 "JOIN users u ON u.id=gc.user_id JOIN concerts c ON c.id=o.concert_id "
                 + ("WHERE gc.status=%s " if status else "") + "ORDER BY gc.created_at DESC",
                 (status,) if status else None)
    return render_template("admin/claims.html", rows=rows, status=status)


@bp.route("/claims/<int:claim_id>", methods=["POST"])
def claim_decide(claim_id):
    claim = query("SELECT * FROM guarantee_claims WHERE id=%s", (claim_id,), one=True)
    if not claim or claim["status"] != "open":
        flash("This claim has already been handled.", "info")
        return redirect(url_for("admin.claims"))
    decision = request.form.get("decision")
    note = request.form.get("note", "").strip()[:255]
    with transaction() as cur:
        if decision == "approve":
            cur.execute("SELECT payment_status FROM orders WHERE id=%s", (claim["order_id"],))
            if cur.fetchone()["payment_status"] == "paid":
                refund_order(cur, claim["order_id"])
            cur.execute("UPDATE guarantee_claims SET status='approved', admin_note=%s WHERE id=%s",
                        (note or "Approved - full refund issued", claim_id))
            flash("Claim approved and the order refunded (demo).", "success")
        else:
            cur.execute("UPDATE guarantee_claims SET status='rejected', admin_note=%s WHERE id=%s",
                        (note or "Rejected", claim_id))
            flash("Claim rejected.", "info")
    return redirect(url_for("admin.claims"))


@bp.route("/messages")
def messages():
    rows = query("SELECT * FROM contact_messages ORDER BY is_read, created_at DESC")
    return render_template("admin/messages.html", rows=rows)


@bp.route("/messages/<int:mid>", methods=["POST"])
def message_action(mid):
    if request.form.get("action") == "delete":
        execute("DELETE FROM contact_messages WHERE id=%s", (mid,))
        flash("Message deleted.", "success")
    else:
        execute("UPDATE contact_messages SET is_read=1-is_read WHERE id=%s", (mid,))
    return redirect(url_for("admin.messages"))
