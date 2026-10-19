"""DEMO payment validation. No money ever moves and no card data is stored
(only the last 4 digits, for the receipt). Swap this module for a real
gateway such as Stripe (test mode) if you take the project further."""
import re
from datetime import date

DECLINE_CARD = "4000000000000002"     # use this number to see a declined payment


def luhn_ok(number):
    digits = [int(c) for c in number][::-1]
    total = 0
    for i, dgt in enumerate(digits):
        if i % 2:
            dgt *= 2
            if dgt > 9:
                dgt -= 9
        total += dgt
    return total % 10 == 0


def card_brand(number):
    if number.startswith("4"):
        return "Visa"
    if re.match(r"5[1-5]|2[2-7]", number):
        return "Mastercard"
    if re.match(r"3[47]", number):
        return "American Express"
    return "Card"


def validate_customer(data):
    errors = {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    if len(name) < 2:
        errors["name"] = "Please enter your full name."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errors["email"] = "Please enter a valid email."
    if not re.fullmatch(r"\+?[\d\s\-()]{7,20}", phone):
        errors["phone"] = "Please enter a valid phone number."
    return errors


def validate_card(card):
    errors = {}
    number = re.sub(r"\D", "", card.get("number") or "")
    expiry = (card.get("expiry") or "").strip()
    cvv = (card.get("cvv") or "").strip()
    holder = (card.get("holder") or "").strip()
    if not 13 <= len(number) <= 19 or not luhn_ok(number):
        errors["number"] = "Card number is not valid."
    m = re.fullmatch(r"(\d{2})\s*/\s*(\d{2})", expiry)
    if not m or not 1 <= int(m.group(1)) <= 12:
        errors["expiry"] = "Use MM/YY."
    else:
        month, year = int(m.group(1)), 2000 + int(m.group(2))
        today = date.today()
        if (year, month) < (today.year, today.month):
            errors["expiry"] = "This card has expired."
    need = 4 if card_brand(number) == "American Express" else 3
    if not re.fullmatch(r"\d{%d}" % need, cvv):
        errors["cvv"] = f"CVV must be {need} digits."
    if len(holder) < 2:
        errors["holder"] = "Enter the name on the card."
    return errors, number


def process_demo_payment(method, card):
    """Return (ok, message, last4)."""
    if method == "card":
        errors, number = validate_card(card or {})
        if errors:
            return False, errors, None
        if number == DECLINE_CARD:
            return False, {"number": "Your bank declined this card (demo decline). Try another card."}, None
        return True, f"{card_brand(number)} ending {number[-4:]}", number[-4:]
    if method in ("apple_pay", "google_pay", "paypal"):
        return True, method, None
    return False, {"method": "Choose a payment method."}, None
