"""AI booking assistant (chat widget).

If ANTHROPIC_API_KEY is set in .env, questions are answered by Claude using
live concert data from MySQL. Otherwise a built-in rule-based assistant
answers common questions, so the feature works offline too.
"""
import re
from datetime import date, timedelta

from flask import Blueprint, current_app, g, jsonify, request, url_for

from db import query
from utils import fmt_date, fmt_time

bp = Blueprint("assistant", __name__)

UPCOMING_SQL = """
SELECT c.id, c.title, c.date, c.time, c.venue, c.city, c.genre, c.age_limit, c.status, a.name AS artist,
  (SELECT MIN(price) FROM tickets t WHERE t.concert_id=c.id AND t.status='available') AS min_price,
  (SELECT COUNT(*) FROM tickets t WHERE t.concert_id=c.id AND t.status='available') AS available
FROM concerts c JOIN artists a ON a.id=c.artist_id
WHERE c.status IN ('on_sale','sold_out') AND c.date >= CURDATE()
ORDER BY c.date
"""

POLICIES = """
- Service fee: a flat 5% of the ticket subtotal, always shown on the seat map and checkout before paying. No other hidden charges.
- Seat holds: selected seats are reserved for 10 minutes during checkout.
- Max 8 tickets per order.
- Zones: VVIP (rows A-B, front seats beside the catwalk), VIP (rows C-E), CAT 1 (rows F-J, raised seating), GA (standing area at the back).
- Payments: credit/debit card, Apple Pay, Google Pay, PayPal. THIS IS A DEMO SITE: no real payments are processed.
- E-tickets: every booking gets a QR-code e-ticket per seat in "My Tickets" and on the confirmation page. Show it at the door.
- Currencies: prices are in SGD; the currency switcher in the header shows SGD, USD, EUR, GBP, MYR, THB and MMK at indicative rates.
- Refunds: full refund (including service fee) if an event is cancelled. Postponed events: keep tickets or request a refund within 14 days of the new date being announced. Otherwise tickets are non-refundable but a Buyer Guarantee claim can be filed.
- Buyer Guarantee: covers invalid tickets, tickets not delivered, and cancelled events. File a claim from the booking's confirmation page (My Bookings > View).
- Accounts: sign up to book. My Bookings shows order history; Favourites saves concerts with the heart icon.
- Contact: support@concerttix.com or the Contact page.
"""


def concert_card(c):
    return {"id": c["id"], "title": c["title"], "artist": c["artist"],
            "date": fmt_date(c["date"], "%a %d %b"), "time": fmt_time(c["time"]),
            "venue": c["venue"], "city": c["city"],
            "min_price": float(c["min_price"]) if c["min_price"] is not None else None,
            "url": url_for("public.concert_detail", concert_id=c["id"])}


# -------------------------------------------------------- Claude (optional)
def ask_claude(message, history, concerts):
    import anthropic

    catalog = "\n".join(
        f"[{c['id']}] {c['artist']} - {c['title']} | {c['date']:%a %d %b %Y} {fmt_time(c['time'])} | "
        f"{c['venue']}, {c['city']} | {c['genre']} | {c['age_limit']} | "
        f"{'from S$%.0f' % c['min_price'] if c['min_price'] else 'SOLD OUT'} | {c['available']} left"
        for c in concerts)
    mine = ""
    if g.user:
        rows = query("SELECT o.order_ref, o.tickets, o.total, o.payment_status, c.title, c.date FROM orders o "
                     "JOIN concerts c ON c.id=o.concert_id WHERE o.user_id=%s ORDER BY o.order_date DESC LIMIT 5",
                     (g.user["id"],))
        mine = "\nThe signed-in user is " + g.user["name"] + ". Their recent bookings:\n" + "\n".join(
            f"- {r['order_ref']}: {r['title']} on {r['date']}, {r['tickets']} tickets, S${r['total']}, {r['payment_status']}"
            for r in rows) if rows else "\nThe signed-in user has no bookings yet."
    system = (
        "You are Tixie, the friendly booking assistant for ConcertTix, a concert ticket website. "
        f"Today is {date.today():%A %d %B %Y}. Answer briefly (2-5 sentences), in plain text with no markdown. "
        "Only recommend concerts from the catalogue below. When you mention a concert, add its tag like "
        "[[concert:ID]] so the site can show a card. Never invent prices or dates.\n\n"
        f"UPCOMING CONCERTS:\n{catalog}\n\nPOLICIES:\n{POLICIES}{mine}")
    msgs = []
    for h in history[-8:]:
        if h.get("role") in ("user", "assistant") and h.get("text"):
            msgs.append({"role": h["role"], "content": str(h["text"])[:1500]})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    msgs.append({"role": "user", "content": message})
    client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
    resp = client.messages.create(model=current_app.config["ANTHROPIC_MODEL"], max_tokens=500,
                                  system=system, messages=msgs)
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    ids = [int(i) for i in re.findall(r"\[\[concert:(\d+)\]\]", text)]
    text = re.sub(r"\s*\[\[concert:\d+\]\]", "", text).strip()
    by_id = {c["id"]: c for c in concerts}
    cards = [concert_card(by_id[i]) for i in dict.fromkeys(ids) if i in by_id][:4]
    return text, cards


# ------------------------------------------------------- built-in fallback
def has(msg, *words):
    return any(re.search(r"\b" + re.escape(w), msg) for w in words)


def rule_based(message, concerts):
    msg = message.lower()
    today = date.today()

    # --- searching for concerts --------------------------------------------
    picked, label = list(concerts), None
    if has(msg, "weekend"):
        sat = today + timedelta(days=(5 - today.weekday()) % 7)
        picked = [c for c in picked if sat - timedelta(days=1) <= c["date"] <= sat + timedelta(days=1)]
        label = "this weekend"
    elif has(msg, "tonight", "today"):
        picked = [c for c in picked if c["date"] == today]
        label = "today"
    elif has(msg, "tomorrow"):
        picked = [c for c in picked if c["date"] == today + timedelta(days=1)]
        label = "tomorrow"
    elif has(msg, "this week", "next 7", "next few days"):
        picked = [c for c in picked if c["date"] <= today + timedelta(days=7)]
        label = "in the next 7 days"
    elif has(msg, "this month", "next month", "month"):
        picked = [c for c in picked if c["date"] <= today + timedelta(days=31)]
        label = "in the next month"
    genre_f = city_f = artist_f = price_f = None
    scan = msg.replace("kpop", "k-pop").replace("jpop", "j-pop")
    for genre in sorted({c["genre"] for c in concerts}, key=len, reverse=True):
        pat = r"(?<![\w-])" + re.escape(genre.lower()) + r"(?![\w-])"
        if re.search(pat, scan):
            genre_f = genre
            picked = [c for c in picked if c["genre"] == genre]
            break
    for city in {c["city"] for c in concerts}:
        if city.lower() in msg:
            city_f = city
            picked = [c for c in picked if c["city"] == city]
    for artist in {c["artist"] for c in concerts}:
        words = artist.lower().split()
        if artist.lower() in msg or (len(words[-1]) > 3 and re.search(r"\b" + re.escape(words[-1]) + r"\b", msg)):
            artist_f = artist
            picked = [c for c in concerts if c["artist"] == artist]
    m = re.search(r"(under|below|less than|cheaper than|max)\s*(s?\$|sgd)?\s*(\d+)", msg)
    if m:
        cap = float(m.group(3))
        price_f = f"under S${cap:.0f}"
        picked = [c for c in picked if c["min_price"] is not None and float(c["min_price"]) <= cap]
    if has(msg, "cheap", "budget", "affordable"):
        picked = sorted([c for c in picked if c["min_price"]], key=lambda c: c["min_price"])
        price_f = price_f or "sorted by lowest price"
    filters = [f for f in (genre_f, city_f, artist_f, price_f) if f]

    searching = label or filters or has(msg, "concert", "show", "event", "gig", "recommend", "what's on",
                                         "whats on", "playing", "perform", "find")
    topic = None
    if has(msg, "refund", "cancel", "postpone", "money back"):
        topic = ("Refunds: if an event is cancelled you get a full refund including the 5% service fee. "
                 "For postponed shows you can keep your tickets or ask for a refund within 14 days of the new "
                 "date. You can file a Buyer Guarantee claim from your booking's page (My Bookings > View). "
                 "Full details are on the Refund Policy page.")
    elif has(msg, "guarantee", "fake", "invalid", "scam", "didn't receive", "not receive", "never got"):
        topic = ("Every order is covered by the ConcertTix Buyer Guarantee: invalid tickets, tickets that "
                 "were not delivered, and cancelled events. Open the booking in My Bookings and click "
                 "\"File a Buyer Guarantee claim\". We review claims within 2 business days.")
    elif has(msg, "fee", "charge", "hidden", "extra cost", "total cost", "how much"):
        topic = ("ConcertTix charges one service fee: 5% of your ticket subtotal. It is shown on the seat map "
                 "summary and again before you pay, so the total you see is the total you pay. For example "
                 "2 seats at S$150 = S$300 + S$15 fee = S$315.")
    elif has(msg, "pay", "card", "paypal", "apple", "google pay", "visa", "mastercard"):
        topic = ("You can pay by credit/debit card, Apple Pay, Google Pay or PayPal. This is a demo site, so "
                 "no real money is taken. Use test card 4242 4242 4242 4242 with any future expiry and CVV.")
    elif has(msg, "currenc", "usd", "myr", "thb", "mmk", "euro", "kyat", "ringgit", "baht"):
        topic = ("Use the currency switcher in the top bar to see prices in SGD, USD, EUR, GBP, MYR, THB or MMK. "
                 "Prices are set in Singapore dollars and converted at indicative rates.")
    elif has(msg, "qr", "e-ticket", "eticket", "my ticket", "where is my", "download", "entry", "door"):
        topic = ("Your QR e-tickets are in My Tickets (and on the booking confirmation page). Each seat has its "
                 "own QR code; show it on your phone at the entrance and staff will scan you in.")
    elif has(msg, "seat", "vvip", "vip", "cat 1", "zone", "general admission", "standing", "section", "view"):
        topic = ("Zones from the stage back: VVIP (rows A-B, beside the catwalk), VIP (rows C-E), CAT 1 (rows F-J, "
                 "raised seating) and GA (standing area). Pick exact seats on the interactive seat map; seats are "
                 "held for 10 minutes while you check out. Max 8 tickets per order.")
    elif has(msg, "age", "kid", "child", "minor", "under 18"):
        topic = ("Age limits are listed on each concert page (e.g. All ages, 12+, 16+, 18+). Under-12s at "
                 "all-ages shows must be accompanied by an adult and still need their own ticket.")
    elif has(msg, "account", "sign up", "signup", "register", "login", "log in", "password"):
        topic = ("Create a free account from Sign up to book tickets, see your booking history and save "
                 "favourites. You can change your password in your Profile.")
    elif has(msg, "booking", "order", "bought", "purchase") and g.user:
        rows = query("SELECT o.order_ref, c.title, c.date FROM orders o JOIN concerts c ON c.id=o.concert_id "
                     "WHERE o.user_id=%s AND o.payment_status='paid' AND c.date>=CURDATE() ORDER BY c.date LIMIT 3",
                     (g.user["id"],))
        topic = ("Your upcoming bookings: " + "; ".join(f"{r['title']} on {fmt_date(r['date'], '%d %b')} "
                 f"({r['order_ref']})" for r in rows) + ". Open My Bookings for details.") if rows else \
            "You don't have any upcoming bookings yet. Want me to suggest a concert?"
    elif has(msg, "contact", "human", "support", "help desk", "email", "phone"):
        topic = "You can reach our team at support@concerttix.com or through the Contact page. We reply within one business day."

    if topic and not (label or filters):
        return topic, []
    if searching or label or filters:
        what = f"{genre_f + ' ' if genre_f else ''}concert"
        tail = "".join([f" by {artist_f}" if artist_f else "", f" in {city_f}" if city_f else "",
                        f" {price_f}" if price_f else "", f" {label}" if label else ""])
        if not picked:
            return (f"I couldn't find any upcoming {what}s{tail}. Here are the next shows on sale instead.",
                    [concert_card(c) for c in concerts[:3]])
        n = len(picked)
        intro = f"I found {n} {what}{'s' if n != 1 else ''}{tail or ' coming up'}."
        avail = [c for c in picked if c["min_price"] is not None]
        if avail:
            cheapest = min(avail, key=lambda c: c["min_price"])
            intro += f" Tickets start from S${float(cheapest['min_price']):.0f} ({cheapest['artist']})."
        else:
            intro += " Unfortunately they're sold out."
        return (topic + "\n\n" + intro if topic else intro), [concert_card(c) for c in picked[:4]]
    if has(msg, "hi", "hello", "hey", "good morning", "good evening"):
        return ("Hi! I'm Tixie, your ConcertTix assistant. Ask me things like \"What's on this weekend?\", "
                "\"K-Pop concerts in Singapore\", \"How much is the service fee?\" or \"How do I get a refund?\""), []
    return ("I can help you find concerts (by date, city, genre, artist or budget) and answer questions about "
            "seats, fees, payments, e-tickets and refunds. Here's what's coming up soon:",
            [concert_card(c) for c in concerts[:3]])


@bp.route("/api/assistant", methods=["POST"])
def assistant():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()[:500]
    if not message:
        return jsonify(ok=False, error="Type a question first."), 400
    concerts = query(UPCOMING_SQL)
    if current_app.config["ANTHROPIC_API_KEY"]:
        try:
            text, cards = ask_claude(message, data.get("history") or [], concerts)
            return jsonify(ok=True, reply=text, concerts=cards, source="claude")
        except Exception as exc:  # fall back silently if the API is unreachable
            current_app.logger.warning("Claude API failed, using fallback: %s", exc)
    text, cards = rule_based(message, concerts)
    return jsonify(ok=True, reply=text, concerts=cards, source="built-in")
