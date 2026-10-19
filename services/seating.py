"""Seat layout, inventory creation and seat holds."""
import secrets
from flask import current_app

from db import query, transaction

# Concert zone layout used for every concert (closest to the stage first).
#   Seated zones: rows x seats per row.  GA = standing spots.
LAYOUT = [
    {"type": "VVIP",              "label": "VVIP",  "note": "Front seats beside the catwalk",
     "rows": ["A", "B"], "seats": 12},
    {"type": "VIP",               "label": "VIP",   "note": "Floor seats, great view of the stage",
     "rows": ["C", "D", "E"], "seats": 16},
    {"type": "CAT 1",             "label": "CAT 1", "note": "Raised seating on the left and right",
     "rows": ["F", "G", "H", "I", "J"], "seats": 20},
    {"type": "General Admission", "label": "GA",    "note": "Standing area, first come first served",
     "standing": 120},
]
TICKET_TYPES = [s["type"] for s in LAYOUT]
DEFAULT_PRICES = {"VVIP": 288, "VIP": 198, "CAT 1": 128, "General Admission": 88}


def build_inventory_rows(concert_id, prices):
    """Return tuples ready for INSERT INTO tickets."""
    rows = []
    for section in LAYOUT:
        price = prices.get(section["type"], DEFAULT_PRICES[section["type"]])
        if "standing" in section:
            for n in range(1, section["standing"] + 1):
                rows.append((concert_id, section["type"], price, f"GA-{n:03d}", None, n))
        else:
            for r in section["rows"]:
                for n in range(1, section["seats"] + 1):
                    rows.append((concert_id, section["type"], price, f"{r}{n}", r, n))
    return rows


INSERT_TICKET_SQL = (
    "INSERT INTO tickets (concert_id, type, price, seat, seat_row, seat_number) "
    "VALUES (%s,%s,%s,%s,%s,%s)"
)


def create_inventory(cur, concert_id, prices):
    cur.executemany(INSERT_TICKET_SQL, build_inventory_rows(concert_id, prices))


def new_qr_token():
    return "CTX-" + secrets.token_hex(8).upper()


def release_expired(cur=None):
    sql = ("UPDATE tickets SET status='available', held_by=NULL, held_until=NULL "
           "WHERE status='held' AND held_until < NOW()")
    if cur is not None:
        cur.execute(sql)
    else:
        with transaction() as c:
            c.execute(sql)


def type_prices(concert_id):
    """Current price per ticket type for a concert."""
    rows = query("SELECT type, MIN(price) AS price FROM tickets WHERE concert_id=%s GROUP BY type",
                 (concert_id,))
    return {r["type"]: float(r["price"]) for r in rows}


class HoldError(Exception):
    pass


def hold_seats(user_id, concert_id, seat_ids, ga_qty):
    """Reserve the chosen seats (and N standing spots) for this user.

    Runs inside one transaction with row locks, so two people can never
    hold or buy the same seat.
    """
    seat_ids = [int(s) for s in seat_ids]
    ga_qty = int(ga_qty or 0)
    total = len(seat_ids) + ga_qty
    max_t = current_app.config["MAX_TICKETS_PER_ORDER"]
    if total == 0:
        raise HoldError("Please select at least one ticket.")
    if total > max_t:
        raise HoldError(f"You can buy up to {max_t} tickets per order.")

    minutes = int(current_app.config["HOLD_MINUTES"])
    with transaction() as cur:
        release_expired(cur)
        # Drop anything this user was already holding for this concert
        cur.execute("UPDATE tickets SET status='available', held_by=NULL, held_until=NULL "
                    "WHERE concert_id=%s AND held_by=%s AND status='held'", (concert_id, user_id))

        if seat_ids:
            ph = ",".join(["%s"] * len(seat_ids))
            cur.execute(f"SELECT id, seat, status, type FROM tickets WHERE concert_id=%s "
                        f"AND id IN ({ph}) FOR UPDATE", [concert_id, *seat_ids])
            found = cur.fetchall()
            if len(found) != len(seat_ids):
                raise HoldError("Some seats could not be found.")
            taken = [f["seat"] for f in found if f["status"] != "available"
                     or f["type"] == "General Admission"]
            if taken:
                raise HoldError("Sorry, these seats were just taken: " + ", ".join(taken)
                                + ". Please choose others.")
            cur.execute(f"UPDATE tickets SET status='held', held_by=%s, "
                        f"held_until=NOW() + INTERVAL %s MINUTE WHERE id IN ({ph})", [user_id, minutes, *seat_ids])

        if ga_qty:
            cur.execute("SELECT id FROM tickets WHERE concert_id=%s AND type='General Admission' "
                        "AND status='available' ORDER BY seat_number LIMIT %s FOR UPDATE",
                        (concert_id, ga_qty))
            ga = [r["id"] for r in cur.fetchall()]
            if len(ga) < ga_qty:
                raise HoldError(f"Only {len(ga)} General Admission spots are left.")
            ph = ",".join(["%s"] * len(ga))
            cur.execute(f"UPDATE tickets SET status='held', held_by=%s, "
                        f"held_until=NOW() + INTERVAL %s MINUTE WHERE id IN ({ph})", [user_id, minutes, *ga])
    return minutes


def held_tickets(user_id, concert_id):
    return query("SELECT *, GREATEST(0, TIMESTAMPDIFF(SECOND, NOW(), held_until)) AS hold_seconds FROM tickets WHERE concert_id=%s AND held_by=%s AND status='held' "
                 "AND held_until > NOW() ORDER BY FIELD(type,'VVIP','VIP','CAT 1',"
                 "'General Admission'), seat_row, seat_number", (concert_id, user_id))


def release_user_holds(user_id, concert_id):
    with transaction() as cur:
        cur.execute("UPDATE tickets SET status='available', held_by=NULL, held_until=NULL "
                    "WHERE concert_id=%s AND held_by=%s AND status='held'", (concert_id, user_id))


def price_breakdown(tickets):
    rate = current_app.config["SERVICE_FEE_RATE"]
    subtotal = round(sum(float(t["price"]) for t in tickets), 2)
    fee = round(subtotal * rate, 2)
    return {"subtotal": subtotal, "service_fee": fee, "total": round(subtotal + fee, 2),
            "count": len(tickets), "fee_rate": rate}
