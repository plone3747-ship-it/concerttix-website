"""Application settings, read from the .env file next to this script."""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

    # MySQL connection
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "concerttix")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "concerttix")

    # Booking rules
    SERVICE_FEE_RATE = 0.05          # 5 % service fee, shown up front
    HOLD_MINUTES = 10                # seats are reserved this long during checkout
    MAX_TICKETS_PER_ORDER = 8

    # Optional AI assistant (Anthropic Claude). Without a key a built-in
    # rule-based assistant answers instead, so the site still works.
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    # Uploads (concert / artist images from the admin panel)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024      # 5 MB
    ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif", "svg"}

    # Display currencies. Prices are stored in SGD; these are fixed,
    # indicative demo rates (1 SGD = x).
    BASE_CURRENCY = "SGD"
    CURRENCIES = {
        "SGD": {"rate": 1.0,    "symbol": "S$",  "decimals": 2},
        "USD": {"rate": 0.77,   "symbol": "US$", "decimals": 2},
        "EUR": {"rate": 0.71,   "symbol": "€",   "decimals": 2},
        "GBP": {"rate": 0.60,   "symbol": "£",   "decimals": 2},
        "MYR": {"rate": 3.45,   "symbol": "RM",  "decimals": 2},
        "THB": {"rate": 26.50,  "symbol": "฿",   "decimals": 0},
        "MMK": {"rate": 1620.0, "symbol": "K",   "decimals": 0},
    }
