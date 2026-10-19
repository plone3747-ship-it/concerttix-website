# ConcertTix – Online Concert Ticket Booking Platform

Final Year Project by **Aung Phone Khant** · Python Flask · MySQL · HTML · CSS · JavaScript

> **Demo / portfolio website.** No real payments are processed and all artists are fictional.

---

## 1. What's included

**Customer site**
- Home, concert listing with search & filters (keyword, city, genre, date range, "this weekend", sort by date/price/popularity), concert detail, artist pages
- **Interactive seat map**: VIP / Premium / Standard seated sections + General Admission standing zone, live availability (refreshes every 20 s), tooltips, unavailable seats disabled, max 8 tickets
- Summary panel with selected seats, ticket count, subtotal, 5% service fee and total. Every fee is shown before checkout.
- 4-step checkout (Select Tickets → Customer Information → Payment → Confirmation) with the order summary on the right, a 10-minute seat-hold timer, demo card validation (Luhn, expiry, CVV), Apple Pay / Google Pay / PayPal simulations
- **QR e-ticket** for every seat (confirmation page, My Tickets, printable)
- Accounts: sign up, log in, My Bookings (history), My Tickets, Favourites, Profile (edit details, change password)
- Reviews & star ratings, favourites (heart button)
- **Buyer Guarantee** claims (invalid ticket / not delivered / cancelled event)
- **Multi-currency** display (SGD, USD, EUR, GBP, MYR, THB, MMK)
- **AI assistant "Tixie"** chat widget (built-in rule-based answers, or Claude API if you add a key)
- About, Contact (saved to database), FAQ, Refund Policy pages
- **Dark / light mode** button (remembers your choice) and a responsive layout for mobile

**Admin dashboard (`/admin`)**
- Stats: Total Sales, Tickets Sold, Total Users, Upcoming Events, Revenue
- Charts: ticket sales (30 days), revenue (6 months), popular concerts, sales by ticket type
- Concerts: add / edit / delete (image upload or auto-generated poster, ticket prices)
- Artists and Venues: add / edit / delete
- Orders: search, filter, detail view, refund, **CSV export**
- Customers: list, detail (orders, reviews, favourites), grant/remove admin role
- Ticket inventory: per-type stock, change prices, block/release seats on a seat map, add/block standing spots
- **Door check-in**: type a ticket code or scan the QR with a camera, prevents double entry
- Buyer Guarantee claims (approve = automatic refund, or reject) and Contact messages

---

## 2. What you need to install (one time)

| Software | Version | Download |
|---|---|---|
| Python | 3.10 or newer | https://www.python.org/downloads/ (Windows: tick **"Add python.exe to PATH"** during install) |
| MySQL Server + MySQL Workbench | 8.0 or newer | https://dev.mysql.com/downloads/installer/ (Windows) or https://dev.mysql.com/downloads/mysql/ (macOS) |
| Visual Studio Code | latest | https://code.visualstudio.com/ |

While installing MySQL, write down the **root password** you choose. You need it in step 4.

Check Python works. Open a terminal (Windows: *PowerShell*; macOS: *Terminal*) and run:

```bash
python --version        # macOS / Linux may need: python3 --version
```

---

## 3. Open the project

1. Unzip `concerttix.zip` somewhere easy, e.g. `C:\Projects\concerttix` or `~/Projects/concerttix`.
2. Open VS Code → **File → Open Folder…** → choose the `concerttix` folder.
3. Open the built-in terminal: **Terminal → New Terminal**. All commands below are typed there.

---

## 4. Create the MySQL database

**Option A – MySQL Workbench (easiest)**
1. Open MySQL Workbench and click your *Local instance* (log in with the root password).
2. **File → Open SQL Script…** → choose `database/create_database.sql`.
3. Click the ⚡ (Execute) button. This creates the `concerttix` database and a user `concerttix` with password `concerttix123`.

**Option B – command line**
```bash
mysql -u root -p < database/create_database.sql
```
(If `mysql` is "not recognized" on Windows, use Option A, or add `C:\Program Files\MySQL\MySQL Server 8.0\bin` to your PATH.)

> Want a different password? Edit it in `create_database.sql` **and** in `.env` (next step).

---

## 5. Set up Python and the project

**Windows (PowerShell)**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```
If PowerShell says *"running scripts is disabled"*, run this once, then activate again:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**macOS / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

You'll see `(venv)` at the start of the terminal line when the virtual environment is active.

Open `.env` in VS Code and check the database settings match step 4:
```
DB_USER=concerttix
DB_PASSWORD=concerttix123
DB_NAME=concerttix
```
Also change `SECRET_KEY` to any long random text.

---

## 6. Create the tables and demo data

```bash
python seed.py
```
Expected output ends with:
```
Done! 15 concerts, 4380 tickets, ~900 orders, 49 customers.
Admin login:    admin@concerttix.com / Admin@123
Customer login: user@concerttix.com  / User@123
```
Run `python seed.py` again any time to **reset** everything back to fresh demo data.

---

## 7. Run the website

```bash
python app.py
```
Open **http://127.0.0.1:5000** in your browser. Press `Ctrl + C` in the terminal to stop.

Next time you only need to:
```bash
.\venv\Scripts\Activate.ps1     # Windows   (macOS: source venv/bin/activate)
python app.py
```

---

## 8. Try it out

| Account | Email | Password |
|---|---|---|
| Customer | `user@concerttix.com` | `User@123` |
| Admin | `admin@concerttix.com` | `Admin@123` |
| Other demo customers | (see Admin → Customers) | `Password@123` |

**Demo payment cards** (any future expiry date such as `12/29`, any CVV such as `123`):
- `4242 4242 4242 4242` → payment succeeds
- `4000 0000 0000 0002` → payment is declined (to show error handling)
- Apple Pay / Google Pay / PayPal → click the button, then **Confirm** in the simulated sheet

**Suggested demo walkthrough**
1. Home → open *Moonlit World Tour 2026* → **Select seats**
2. Click two seats + add one General Admission → watch the summary (subtotal, 5% fee, total)
3. Continue → log in as the customer → you return to your seats → **Continue to checkout**
4. Fill in details → pay with `4242…` → confirmation with QR e-tickets
5. Switch currency (top bar) and dark mode (moon icon)
6. Ask Tixie: *"What's on this weekend?"*, *"K-Pop concerts in Singapore"*, *"How do refunds work?"*
7. Log in as admin → Dashboard → **Door check-in** → paste a ticket code (e.g. `CTX-…` from the e-ticket) → *Admit*. Try it again → *Already used*.
8. Admin → **Guarantee claims** → approve the open claim → the order is refunded and the seats go back on sale.

---

## 9. Optional: real AI answers with Claude

The assistant works without any key (built-in answers using live data from MySQL). To use Claude instead:
1. Create an API key at https://console.anthropic.com/
2. In `.env` set `ANTHROPIC_API_KEY=sk-ant-...`
3. Restart `python app.py`

If the API can't be reached, the site automatically falls back to the built-in assistant.

---

## 10. Project structure

```
concerttix/
├── app.py                 # Flask app: blueprints, filters, error pages
├── config.py              # settings (reads .env): fees, hold time, currencies
├── db.py                  # MySQL helper (PyMySQL): query / execute / transaction
├── seed.py                # creates tables + realistic Singapore demo data
├── utils.py               # login/admin checks, CSRF protection, uploads, formatting
├── requirements.txt
├── .env.example
├── database/
│   ├── create_database.sql   # creates DB + user (run once as root)
│   └── schema.sql            # all tables
├── routes/
│   ├── public.py          # home, concerts, detail, artists, reviews, favourites, info pages
│   ├── auth.py            # login, signup, logout
│   ├── booking.py         # seat map API, seat holds, checkout, payment, confirmation, QR codes
│   ├── account.py         # my bookings, my tickets, favourites, profile, guarantee claims
│   └── assistant.py       # AI assistant API
├── admin/routes.py        # everything under /admin
├── services/
│   ├── seating.py         # venue layout, inventory, 10-minute seat holds (row locking)
│   ├── payments.py        # DEMO payment validation (no real charges)
│   └── posters.py         # generates branded SVG posters / artist images
├── templates/             # Jinja2 HTML (base, pages, auth/, account/, admin/)
└── static/
    ├── css/style.css      # design system, light + dark themes
    ├── js/main.js         # theme, currency, menus, favourites, chat
    ├── js/seatmap.js      # interactive seat selection
    ├── js/checkout.js     # checkout steps + payment
    ├── js/admin.js        # dashboard charts, inventory map, check-in scanner
    ├── vendor/            # Chart.js and html5-qrcode (bundled so it works offline)
    └── img/               # logo, favicon, generated posters
```

---

## 11. Database tables

| Table | Key columns |
|---|---|
| `users` | id, name, email, phone, password (hashed), role (`customer`/`admin`) |
| `artists` | id, name, image, genre, description |
| `venues` | id, name, address, city, capacity |
| `concerts` | id, artist_id, venue_id, title, image, date, time, venue, city, genre, age_limit, description, status |
| `tickets` | id, concert_id, type, price, seat, status (`available`/`held`/`sold`/`blocked`), held_by, held_until, order_id, qr_token, checked_in_at |
| `orders` | id, order_ref, user_id, concert_id, tickets, subtotal, service_fee, total, currency, payment_method, payment_status, order_date |
| `reviews` | user_id, concert_id, rating, comment |
| `favorites` | user_id, concert_id |
| `guarantee_claims` | order_id, user_id, reason, status, admin_note |
| `contact_messages` | name, email, subject, message, is_read |

Prices are stored in **SGD**. Each seat is one row in `tickets`. When a customer continues to checkout the seats become `held` for 10 minutes inside a database transaction with row locks (`SELECT … FOR UPDATE`), so two people can never buy the same seat.

**Security basics included:** salted password hashing (Werkzeug), CSRF tokens on every form and API call, parameterised SQL queries (no SQL injection), admin-only route guard, only safe redirects after login, upload type/size checks, card numbers never stored (only the last 4 digits).

---

## 12. Troubleshooting

| Problem | Fix |
|---|---|
| `Access denied for user 'concerttix'@'localhost'` | Password in `.env` doesn't match `create_database.sql`. Re-run step 4 or fix `.env`. |
| `Can't connect to MySQL server on 'localhost'` | MySQL isn't running. Windows: *Services → MySQL80 → Start*. macOS: *System Settings → MySQL → Start*. |
| `Unknown database 'concerttix'` | Step 4 wasn't run. |
| `'cryptography' package is required` | `pip install cryptography` (inside the venv). |
| `ModuleNotFoundError: No module named 'flask'` | The venv isn't active. Activate it (step 5) and retry. |
| `Address already in use` / port 5000 busy (common on macOS, AirPlay uses it) | Run `flask --app app run --port 5050` and open http://127.0.0.1:5050 |
| Camera scanner doesn't start | Browsers only allow cameras on `localhost`/HTTPS. Allow camera access, or type the ticket code. |
| Fonts look different | The Manrope font loads from Google Fonts. Offline, the site uses your system font. |

---

## 13. Ideas for the final report / future work
- Connect a real payment sandbox (Stripe test mode) in `services/payments.py`
- Email the e-tickets (Flask-Mail) after payment
- Live exchange rates from an API instead of fixed demo rates
- Seat-map layouts per venue (stored in the database) instead of one shared layout
- Automated tests with `pytest`, and deployment (e.g. PythonAnywhere, Render, or a VPS with Gunicorn + Nginx)
