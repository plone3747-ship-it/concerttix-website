"""Create all tables and fill them with realistic demo data.

    python seed.py

WARNING: this drops and recreates every ConcertTix table.
"""
import os
import random
import re
import sys
from datetime import date, datetime, time, timedelta

from werkzeug.security import generate_password_hash

from config import BASE_DIR, Config
from db import connect
from services.posters import artist_svg, poster_svg, save_svg
from services.seating import build_inventory_rows, new_qr_token, INSERT_TICKET_SQL

STATIC = os.path.join(BASE_DIR, "static")
random.seed(42)
TODAY = date.today()


def d(days):
    return TODAY + timedelta(days=days)


VENUES = [
    ("Singapore Indoor Stadium", "2 Stadium Walk, Singapore 397691", "Singapore", 12000),
    ("The Star Theatre", "1 Vista Exchange Green, Singapore 138617", "Singapore", 5000),
    ("Esplanade Concert Hall", "1 Esplanade Drive, Singapore 038981", "Singapore", 1600),
    ("National Stadium", "1 Stadium Drive, Singapore 397629", "Singapore", 55000),
    ("Capitol Theatre", "17 Stamford Road, Singapore 178907", "Singapore", 900),
    ("Axiata Arena", "Jalan Barat, Bukit Jalil, 57000 Kuala Lumpur", "Kuala Lumpur", 16000),
    ("Impact Arena", "99 Popular Road, Pak Kret, Nonthaburi 11120", "Bangkok", 12000),
    ("Thuwunna National Indoor Stadium", "Thuwunna, Thingangyun Township, Yangon", "Yangon", 8000),
]

ARTISTS = [
    ("Luna Vale", "Pop", "Singapore-born pop vocalist known for shimmering synth-pop anthems and "
     "a stage show built around light and movement. Her debut album topped regional charts for 11 weeks."),
    ("Seoul Bloom", "K-Pop", "Seven-member K-Pop group famous for razor-sharp choreography, "
     "bright fan chants and a live band that reworks their hits for the stage."),
    ("The Midnight Static", "Indie Rock", "Four-piece indie rock band from Melbourne mixing jangly "
     "guitars, fuzzed-out bass and sing-along choruses."),
    ("Echo Harbour", "Electronic", "Audio-visual electronic duo whose live sets fuse modular synths, "
     "field recordings and immersive projection."),
    ("Marigold Strings Orchestra", "Classical", "A 60-piece chamber orchestra performing film scores "
     "and reimagined pop classics alongside the great symphonic works."),
    ("Nadia Rahman Quartet", "Jazz", "Pianist Nadia Rahman leads a tight quartet through modern jazz "
     "originals and Southeast Asian standards."),
    ("Kaito Ren", "J-Pop", "Tokyo singer-songwriter and producer whose neon-tinted J-Pop has racked "
     "up hundreds of millions of streams."),
    ("Bassline Theory", "EDM", "Festival-headlining DJ and producer collective delivering high-energy "
     "big-room and melodic house sets."),
    ("Aria Sen", "R&B", "Smooth, soulful R&B with a live horn section. Aria's intimate shows are "
     "known for unexpected acoustic encores."),
    ("Shwe Ya Min", "Myanmar Pop", "Yangon's beloved pop star blending traditional Myanmar melodies "
     "with modern production."),
    ("Iron Lotus", "Rock", "Hard-hitting Asian rock outfit with soaring vocals, twin guitars and an "
     "unforgettable pyrotechnic show."),
]

# (artist_idx, venue_idx, title, day_offset, hh:mm, prices(VIP,Prem,Std,GA), age, status, featured, sold_ratio)
CONCERTS = [
    (0, 0, "Moonlit World Tour 2026", 16, "20:00", (288, 198, 128, 88), "All ages", "on_sale", 1, 0.55),
    (1, 3, "BLOOM Live in Singapore", 37, "19:30", (348, 248, 168, 118), "All ages", "on_sale", 1, 0.82),
    (2, 4, "Static Nights", 9, "20:00", (168, 128, 98, 68), "16+", "on_sale", 0, 0.45),
    (3, 1, "Tidal Live: Audio-Visual Show", 24, "21:00", (198, 148, 108, 78), "18+", "on_sale", 0, 0.35),
    (4, 2, "Symphony Under the Stars", 3, "19:30", (150, 120, 90, 60), "All ages", "on_sale", 1, 0.62),
    (5, 4, "Late Night Jazz Sessions", 2, "20:30", (120, 95, 75, 55), "12+", "on_sale", 0, 0.5),
    (6, 5, "Neon Horizon Asia Tour - Kuala Lumpur", 58, "19:00", (268, 188, 128, 88), "All ages", "on_sale", 0, 0.3),
    (7, 0, "Countdown 2027", 84, "21:00", (258, 178, 118, 78), "18+", "on_sale", 1, 0.4),
    (8, 1, "Velvet Hours", 107, "20:00", (218, 158, 108, 78), "All ages", "on_sale", 0, 0.2),
    (9, 7, "Golden Land Live", 51, "18:30", (120, 90, 60, 40), "All ages", "on_sale", 0, 0.38),
    (10, 6, "Thunder in Bangkok", 128, "19:00", (238, 168, 118, 78), "16+", "on_sale", 0, 0.15),
    (6, 0, "Neon Horizon Asia Tour - Singapore", 65, "19:30", (278, 198, 138, 98), "All ages", "on_sale", 1, 0.48),
    (2, 2, "Summer Static", -47, "20:00", (158, 118, 88, 58), "16+", "completed", 0, 0.88),
    (8, 4, "Velvet Hours: Intimate Preview", -26, "20:00", (188, 138, 98, 68), "All ages", "completed", 0, 0.9),
    (10, 1, "Thunder in Singapore", 23, "20:00", (228, 158, 108, 78), "16+", "cancelled", 0, 0.3),
]

DESCRIPTIONS = {
    "Pop": "An arena-sized night of glittering pop, choreographed light shows and every chart hit fans have been waiting to sing along to.",
    "K-Pop": "Expect full-production staging, fan-chant favourites and brand-new choreography premiered live for the first time in Southeast Asia.",
    "Indie Rock": "Loud guitars, sweaty choruses and an encore you will hear about for weeks. Doors open one hour before the show.",
    "Electronic": "A 90-minute immersive audio-visual performance with 360-degree projection and a custom spatial sound system.",
    "Classical": "Iconic film scores and symphonic favourites performed live, with a special guest soloist for the second half.",
    "Jazz": "Two intimate sets of modern jazz and Southeast Asian standards. Bar service available throughout the night.",
    "J-Pop": "Neon visuals, live band arrangements and a setlist spanning the debut album to the latest singles.",
    "EDM": "Ring in the new year with a five-hour countdown party featuring pyrotechnics, CO2 jets and confetti at midnight.",
    "R&B": "Velvet vocals, a live horn section and stripped-back acoustic moments in an unforgettable evening of soul.",
    "Myanmar Pop": "A celebration of Myanmar pop with traditional instruments, special guests and the hits the whole country knows.",
    "Rock": "Twin guitars, thunderous drums and a full pyrotechnic production. Earplugs recommended.",
}

FIRST = ["Wei Ling", "Jun Hao", "Siti", "Arjun", "Mei", "Daniel", "Nur Aisyah", "Ethan", "Priya", "Marcus",
         "Hui Min", "Ryan", "Farah", "Kenji", "Chloe", "Aung", "Thandar", "Zhi Wei", "Hannah", "Rahul",
         "Jasmine", "Ming", "Sophia", "Irfan", "Khin", "Lucas", "Aditi", "Yuki", "Isabel", "Hafiz"]
LAST = ["Tan", "Lim", "Ng", "Lee", "Wong", "Kumar", "Rahman", "Chua", "Goh", "Ong", "Teo", "Koh",
        "Menon", "Ismail", "Htet", "Zaw", "Sato", "Fernandez", "Yeo", "Pillai"]

REVIEW_TEXT = [
    (5, "Absolutely incredible night. The sound was crystal clear and the seat map showed exactly where I'd be."),
    (5, "Best concert I've been to this year. Entry with the QR code took seconds."),
    (4, "Amazing performance. Queue for merch was long but the show itself was flawless."),
    (5, "Goosebumps from start to finish. Worth every dollar."),
    (4, "Great setlist and lighting. Would love a longer encore next time!"),
    (3, "Good show, but the standing area got very crowded near the front."),
    (5, "The band sounded even better live. Booking was super easy too."),
    (4, "Lovely venue and friendly staff. Seats in VIP had a perfect view."),
]


def sql_statements(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"--[^\n]*", "", text)
    return [s.strip() for s in text.split(";") if s.strip()]


def order_ref(n):
    return f"CTX{TODAY:%y}{n:05d}"


def main():
    conn = connect(Config)
    cur = conn.cursor()
    print("Creating tables ...")
    for stmt in sql_statements(os.path.join(BASE_DIR, "database", "schema.sql")):
        cur.execute(stmt)

    conn.autocommit(False)

    print("Users ...")
    cur.execute("INSERT INTO users (name,email,phone,password,role,created_at) VALUES (%s,%s,%s,%s,'admin',%s)",
                ("ConcertTix Admin", "admin@concerttix.com", "+65 6123 4567",
                 generate_password_hash("Admin@123"), datetime.now() - timedelta(days=120)))
    cur.execute("INSERT INTO users (name,email,phone,password,role,created_at) VALUES (%s,%s,%s,%s,'customer',%s)",
                ("Aung Phone Khant", "user@concerttix.com", "+65 8123 4567",
                 generate_password_hash("User@123"), datetime.now() - timedelta(days=90)))
    demo_user = cur.lastrowid
    shared_hash = generate_password_hash("Password@123")
    customers = [demo_user]
    used = set()
    for i in range(48):
        while True:
            name = f"{random.choice(FIRST)} {random.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        email = name.lower().replace(" ", ".") + f"{i}@example.com"
        phone = f"+65 {random.choice([8, 9])}{random.randint(100, 999)} {random.randint(1000, 9999)}"
        cur.execute("INSERT INTO users (name,email,phone,password,role,created_at) VALUES (%s,%s,%s,%s,'customer',%s)",
                    (name, email, phone, shared_hash, datetime.now() - timedelta(days=random.randint(1, 110))))
        customers.append(cur.lastrowid)

    print("Venues and artists ...")
    venue_ids = []
    for v in VENUES:
        cur.execute("INSERT INTO venues (name,address,city,capacity) VALUES (%s,%s,%s,%s)", v)
        venue_ids.append(cur.lastrowid)
    artist_ids = []
    for i, (name, genre, desc) in enumerate(ARTISTS):
        cur.execute("INSERT INTO artists (name,genre,description) VALUES (%s,%s,%s)", (name, genre, desc))
        aid = cur.lastrowid
        img = save_svg(STATIC, "artists", f"artist-{aid}.svg", artist_svg(name, aid))
        cur.execute("UPDATE artists SET image=%s WHERE id=%s", (img, aid))
        artist_ids.append(aid)

    print("Concerts and seat inventory ...")
    order_no = 0
    concert_rows = []
    for idx, (ai, vi, title, off, hhmm, prices, age, status, featured, ratio) in enumerate(CONCERTS):
        artist = ARTISTS[ai]
        venue = VENUES[vi]
        cdate = d(off)
        h, m = map(int, hhmm.split(":"))
        cur.execute("INSERT INTO concerts (artist_id,venue_id,title,date,time,venue,city,genre,age_limit,"
                    "description,status,featured) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (artist_ids[ai], venue_ids[vi], title, cdate, time(h, m), venue[0], venue[2],
                     artist[1], age, DESCRIPTIONS[artist[1]], status, featured))
        cid = cur.lastrowid
        img = save_svg(STATIC, "posters", f"concert-{cid}.svg",
                       poster_svg(title, artist[0], cdate.strftime("%a %d %b %Y").upper(), venue[0], cid))
        cur.execute("UPDATE concerts SET image=%s WHERE id=%s", (img, cid))
        price_map = dict(zip(["VVIP", "VIP", "CAT 1", "General Admission"], prices))
        cur.executemany(INSERT_TICKET_SQL, build_inventory_rows(cid, price_map))
        concert_rows.append((cid, cdate, status, ratio, price_map))

        # A few seats taken off sale (production / camera position)
        cur.execute("UPDATE tickets SET status='blocked' WHERE concert_id=%s AND seat IN ('J1','J2','J19','J20')", (cid,))

    # ---- Demo customer's own bookings ------------------------------------------------
    print("Demo customer bookings, reviews, favourites ...")
    now = datetime.now()

    def demo_order(cid, seats, days_ago, pstatus="paid"):
        nonlocal order_no
        cur.execute("SELECT id, price FROM tickets WHERE concert_id=%s AND seat IN (" +
                    ",".join(["%s"] * len(seats)) + ")", [cid, *seats])
        ts = cur.fetchall()
        subtotal = round(sum(float(t["price"]) for t in ts), 2)
        fee = round(subtotal * Config.SERVICE_FEE_RATE, 2)
        order_no += 1
        cur.execute("INSERT INTO orders (order_ref,user_id,concert_id,tickets,subtotal,service_fee,total,currency,"
                    "total_in_currency,customer_name,customer_email,customer_phone,payment_method,card_last4,"
                    "payment_status,order_date) VALUES (%s,%s,%s,%s,%s,%s,%s,'SGD',%s,%s,%s,%s,'card','4242',%s,%s)",
                    (order_ref(order_no), demo_user, cid, len(ts), subtotal, fee, subtotal + fee, subtotal + fee,
                     "Aung Phone Khant", "user@concerttix.com", "+65 8123 4567", pstatus,
                     now - timedelta(days=days_ago)))
        oid = cur.lastrowid
        for t in ts:
            cur.execute("UPDATE tickets SET status='sold', order_id=%s, qr_token=%s, held_by=NULL WHERE id=%s",
                        (oid, new_qr_token(), t["id"]))
        return oid

    c = {i + 1: row[0] for i, row in enumerate(concert_rows)}
    demo_order(c[1], ["A11", "A12"], 12)
    demo_order(c[5], ["C7"], 4)
    past = demo_order(c[13], ["F9", "F10"], 70)
    cur.execute("UPDATE tickets SET checked_in_at=%s WHERE order_id=%s",
                (datetime.combine(d(-47), time(19, 12)), past))
    cancelled_order = demo_order(c[15], ["D4", "D5"], 20)
    cur.execute("INSERT INTO guarantee_claims (order_id,user_id,reason,details,status) VALUES (%s,%s,'event_cancelled',%s,'open')",
                (cancelled_order, demo_user, "The Iron Lotus Singapore show was cancelled. Requesting a full refund under the Buyer Guarantee."))
    for cid in (c[2], c[8], c[12]):
        cur.execute("INSERT INTO favorites (user_id, concert_id) VALUES (%s,%s)", (demo_user, cid))

    print("Orders ...")
    for cid, cdate, status, ratio, price_map in concert_rows:
        cur.execute("SELECT id, type, price, seat, seat_row, seat_number FROM tickets "
                    "WHERE concert_id=%s AND status='available' ORDER BY id", (cid,))
        avail = cur.fetchall()
        by_row = {}
        for t in avail:
            key = t["seat_row"] or "GA"
            by_row.setdefault(key, []).append(t)
        target = int(len(avail) * ratio)
        sold = 0
        sale_start = datetime.combine(cdate, time(12)) - timedelta(days=75)
        sale_end = min(now, datetime.combine(cdate, time(12)) - timedelta(hours=6))
        if sale_start > sale_end:
            sale_start = sale_end - timedelta(days=30)
        span = (sale_end - sale_start).total_seconds()
        while sold < target:
            row_key = random.choice(list(by_row.keys()) + ["GA", "GA"])
            pool = by_row.get(row_key) or []
            if not pool:
                if not any(by_row.values()):
                    break
                continue
            qty = min(random.choice([1, 2, 2, 2, 3, 4]), len(pool), target - sold)
            if row_key == "GA":
                picked = pool[:qty]
            else:
                start = random.randint(0, len(pool) - qty)
                picked = pool[start:start + qty]
            for p in picked:
                pool.remove(p)
            sold += len(picked)
            uid = random.choice(customers[1:])
            cur.execute("SELECT name,email,phone FROM users WHERE id=%s", (uid,))
            u = cur.fetchone()
            # sales cluster closer to the on-sale date and the show date
            r = random.random()
            when = sale_start + timedelta(seconds=span * (r ** 1.6 if random.random() < .6 else 1 - r ** 2))
            subtotal = round(sum(float(p["price"]) for p in picked), 2)
            fee = round(subtotal * Config.SERVICE_FEE_RATE, 2)
            method = random.choice(["card", "card", "card", "apple_pay", "google_pay", "paypal"])
            pstatus = "paid"
            if status == "cancelled":
                pstatus = random.choice(["refunded", "refunded", "paid"])
            order_no += 1
            cur.execute("INSERT INTO orders (order_ref,user_id,concert_id,tickets,subtotal,service_fee,total,currency,"
                        "total_in_currency,customer_name,customer_email,customer_phone,payment_method,card_last4,"
                        "payment_status,order_date) VALUES (%s,%s,%s,%s,%s,%s,%s,'SGD',%s,%s,%s,%s,%s,%s,%s,%s)",
                        (order_ref(order_no), uid, cid, len(picked), subtotal, fee, subtotal + fee, subtotal + fee,
                         u["name"], u["email"], u["phone"], method,
                         f"{random.randint(0, 9999):04d}" if method == "card" else None, pstatus, when))
            oid = cur.lastrowid
            for p in picked:
                checked = None
                if status == "completed" and random.random() < 0.93:
                    checked = datetime.combine(cdate, time(18)) + timedelta(minutes=random.randint(0, 120))
                tstatus = "available" if pstatus == "refunded" else "sold"
                cur.execute("UPDATE tickets SET status=%s, order_id=%s, qr_token=%s, checked_in_at=%s WHERE id=%s",
                            (tstatus, oid if tstatus == "sold" else None,
                             new_qr_token() if tstatus == "sold" else None, checked, p["id"]))

    # Reviews on past concerts (from people who bought tickets)
    for cid, cdate, status, *_ in concert_rows:
        if status != "completed":
            continue
        cur.execute("SELECT DISTINCT user_id FROM orders WHERE concert_id=%s AND user_id<>%s LIMIT 9", (cid, demo_user))
        for i, r in enumerate(cur.fetchall()):
            rating, text = REVIEW_TEXT[i % len(REVIEW_TEXT)]
            cur.execute("INSERT INTO reviews (user_id,concert_id,rating,comment,created_at) VALUES (%s,%s,%s,%s,%s)",
                        (r["user_id"], cid, rating, text, datetime.combine(cdate, time(23)) + timedelta(days=random.randint(1, 6))))
    cur.execute("INSERT INTO reviews (user_id,concert_id,rating,comment,created_at) VALUES (%s,%s,5,%s,%s)",
                (demo_user, c[13], "Front-row energy even from row F. Can't wait for the next tour!", now - timedelta(days=45)))

    # Sync concert status for anything that sold out
    cur.execute("UPDATE concerts c SET status='sold_out' WHERE status='on_sale' AND NOT EXISTS "
                "(SELECT 1 FROM tickets t WHERE t.concert_id=c.id AND t.status='available')")

    print("Contact messages ...")
    msgs = [
        ("Mei Tan", "mei.tan@example.com", "Wheelchair access at National Stadium",
         "Hi, are there wheelchair-accessible seats for the Seoul Bloom concert? Thanks!"),
        ("Rahul Menon", "rahul.m@example.com", "Change the name on my ticket",
         "I bought 2 tickets for Countdown 2027 but my friend can't go. Can I transfer one?"),
        ("Yuki Sato", "yuki.sato@example.com", "Group booking",
         "We are a group of 12 from our office. Do you offer group discounts?"),
    ]
    for i, m in enumerate(msgs):
        cur.execute("INSERT INTO contact_messages (name,email,subject,message,created_at) VALUES (%s,%s,%s,%s,%s)",
                    (*m, now - timedelta(days=i * 2 + 1)))

    conn.commit()
    cur.execute("SELECT COUNT(*) n FROM orders")
    n_orders = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) n FROM tickets")
    n_t = cur.fetchone()["n"]
    conn.close()
    print(f"\nDone! {len(CONCERTS)} concerts, {n_t} tickets, {n_orders} orders, {len(customers)} customers.")
    print("Admin login:    admin@concerttix.com / Admin@123")
    print("Customer login: user@concerttix.com  / User@123")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # friendly message for the common setup errors
        print("\nSeeding failed:", exc)
        print("Check that MySQL is running and that the DB_* values in your .env file are correct.")
        sys.exit(1)
