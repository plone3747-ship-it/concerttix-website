"""Seat selection, checkout, demo payment, confirmation and QR e-tickets."""
import io
import secrets
from datetime import date

import qrcode
import qrcode.image.svg
from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify,
                   redirect, render_template, request, session, url_for)

from db import query, transaction
from services import seating
from services.payments import process_demo_payment, validate_customer
from utils import login_required

bp = Blueprint("booking", __name__)


def get_concert(concert_id):
    c = query("SELECT c.*, a.name AS artist_name FROM concerts c JOIN artists a ON a.id=c.artist_id "
              "WHERE c.id=%s", (concert_id,), one=True)
    if not c:
        abort(404)
    return c


def bookable(c):
    return c["status"] == "on_sale" and c["date"] >= date.today()


# ------------------------------------------------------------ seat map
def seat_payload(concert_id):
    seating.release_expired()
    uid = g.user["id"] if g.user else -1
    rows = query("SELECT id, seat, seat_row, seat_number, type, price, status, held_by "
                 "FROM tickets WHERE concert_id=%s ORDER BY id", (concert_id,))
    seats, ga = [], {"available": 0, "price": 0, "total": 0, "mine": 0}
    for r in rows:
        mine = r["status"] == "held" and r["held_by"] == uid
        if r["type"] == "General Admission":
            ga["total"] += 1
            ga["price"] = float(r["price"])
            if r["status"] == "available":
                ga["available"] += 1
            if mine:
                ga["mine"] += 1
            continue
        state = "mine" if mine else ("available" if r["status"] == "available" else "taken")
        seats.append({"id": r["id"], "seat": r["seat"], "row": r["seat_row"], "n": r["seat_number"],
                      "type": r["type"], "price": float(r["price"]), "state": state})
    return {"seats": seats, "ga": ga}


@bp.route("/concerts/<int:concert_id>/seats")
def seats(concert_id):
    c = get_concert(concert_id)
    if c["status"] == "draft":
        abort(404)
    return render_template("seats.html", c=c, can_book=bookable(c), data=seat_payload(concert_id),
                           layout=seating.LAYOUT, max_tickets=current_app.config["MAX_TICKETS_PER_ORDER"])


@bp.route("/api/concerts/<int:concert_id>/seats")
def seats_api(concert_id):
    get_concert(concert_id)
    return jsonify(seat_payload(concert_id))


@bp.route("/api/concerts/<int:concert_id>/hold", methods=["POST"])
@login_required
def hold(concert_id):
    c = get_concert(concert_id)
    if not bookable(c):
        return jsonify(ok=False, error="Tickets for this concert are not on sale."), 400
    data = request.get_json(silent=True) or {}
    try:
        seating.hold_seats(g.user["id"], concert_id, data.get("seats", []), data.get("ga", 0))
    except seating.HoldError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Invalid selection."), 400
    return jsonify(ok=True, redirect=url_for("booking.checkout", concert_id=concert_id))


@bp.route("/api/concerts/<int:concert_id>/release", methods=["POST"])
@login_required
def release(concert_id):
    seating.release_user_holds(g.user["id"], concert_id)
    return jsonify(ok=True)


# ------------------------------------------------------------ checkout
@bp.route("/checkout/<int:concert_id>")
@login_required
def checkout(concert_id):
    c = get_concert(concert_id)
    seating.release_expired()
    tickets = seating.held_tickets(g.user["id"], concert_id)
    if not tickets:
        flash("Your seat reservation has expired or is empty. Please pick your seats again.", "info")
        return redirect(url_for("booking.seats", concert_id=concert_id))
    summary = seating.price_breakdown(tickets)
    hold_seconds = min(int(t["hold_seconds"]) for t in tickets)
    return render_template("checkout.html", c=c, tickets=tickets, summary=summary,
                           hold_seconds=hold_seconds)


@bp.route("/api/checkout/<int:concert_id>/pay", methods=["POST"])
@login_required
def pay(concert_id):
    c = get_concert(concert_id)
    if not bookable(c):
        return jsonify(ok=False, error="Tickets for this concert are no longer on sale."), 400
    data = request.get_json(silent=True) or {}
    customer = data.get("customer") or {}
    errors = validate_customer(customer)
    if errors:
        return jsonify(ok=False, step=2, errors=errors, error="Please check your details."), 400
    method = data.get("method")
    ok, result, last4 = process_demo_payment(method, data.get("card"))
    if not ok:
        return jsonify(ok=False, step=3, errors=result, error="Payment could not be completed."), 402

    cur_code = data.get("currency") if data.get("currency") in current_app.config["CURRENCIES"] else "SGD"
    rate = current_app.config["CURRENCIES"][cur_code]["rate"]
    with transaction() as cur:
        cur.execute("SELECT * FROM tickets WHERE concert_id=%s AND held_by=%s AND status='held' "
                    "AND held_until > NOW() FOR UPDATE", (concert_id, g.user["id"]))
        tickets = cur.fetchall()
        if not tickets:
            return jsonify(ok=False, step=1, expired=True,
                           error="Your 10-minute seat hold expired. Please choose your seats again.",
                           redirect=url_for("booking.seats", concert_id=concert_id)), 409
        s = seating.price_breakdown(tickets)
        ref = "CTX" + date.today().strftime("%y") + secrets.token_hex(3).upper()
        cur.execute("INSERT INTO orders (order_ref,user_id,concert_id,tickets,subtotal,service_fee,total,currency,"
                    "total_in_currency,customer_name,customer_email,customer_phone,payment_method,card_last4,"
                    "payment_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'paid')",
                    (ref, g.user["id"], concert_id, s["count"], s["subtotal"], s["service_fee"], s["total"],
                     cur_code, round(s["total"] * rate, 2), customer["name"].strip(),
                     customer["email"].strip(), customer["phone"].strip(), method, last4))
        order_id = cur.lastrowid
        for t in tickets:
            cur.execute("UPDATE tickets SET status='sold', order_id=%s, qr_token=%s, held_by=NULL, "
                        "held_until=NULL WHERE id=%s", (order_id, seating.new_qr_token(), t["id"]))
        cur.execute("UPDATE concerts SET status='sold_out' WHERE id=%s AND status='on_sale' AND NOT EXISTS "
                    "(SELECT 1 FROM tickets WHERE concert_id=%s AND status IN ('available','held'))",
                    (concert_id, concert_id))
    session["currency"] = cur_code
    return jsonify(ok=True, order_ref=ref, seats=[t["seat"] for t in tickets],
                   total=s["total"], currency=cur_code,
                   confirmation_url=url_for("booking.confirmation", ref=ref))


# -------------------------------------------------------- confirmation
def load_order(ref):
    o = query("SELECT o.*, c.title, c.date, c.time, c.venue, c.city, c.image, c.status AS concert_status, "
              "c.age_limit, a.name AS artist_name FROM orders o JOIN concerts c ON c.id=o.concert_id "
              "JOIN artists a ON a.id=c.artist_id WHERE o.order_ref=%s", (ref,), one=True)
    if not o or (o["user_id"] != g.user["id"] and g.user["role"] != "admin"):
        abort(404)
    return o


@bp.route("/confirmation/<ref>")
@login_required
def confirmation(ref):
    o = load_order(ref)
    tickets = query("SELECT * FROM tickets WHERE order_id=%s ORDER BY FIELD(type,'VVIP','VIP','CAT 1',"
                    "'General Admission'), seat_row, seat_number", (o["id"],))
    claim = query("SELECT * FROM guarantee_claims WHERE order_id=%s ORDER BY id DESC LIMIT 1", (o["id"],), one=True)
    return render_template("confirmation.html", o=o, tickets=tickets, claim=claim,
                           just_booked=request.args.get("new") == "1")


@bp.route("/tickets/<token>/qr.svg")
@login_required
def ticket_qr(token):
    t = query("SELECT t.qr_token, o.user_id FROM tickets t JOIN orders o ON o.id=t.order_id "
              "WHERE t.qr_token=%s", (token,), one=True)
    if not t or (t["user_id"] != g.user["id"] and g.user["role"] != "admin"):
        abort(404)
    img = qrcode.make(token, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), mimetype="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=86400"})
