"""Upgrade an EXISTING ConcertTix database to the new concert zones.

    Old ticket types  ->  New zones
    VIP               ->  VVIP
    Premium           ->  VIP
    Standard          ->  CAT 1
    General Admission ->  General Admission (GA, unchanged)

Your artists, concerts, photos, users and orders are all kept.
Run once:   python migrate_zones.py      (or double-click update_zones.bat)
Fresh installs (setup.bat / seed.py) already use the new zones.
"""
import sys

from config import Config
from db import connect

NEW_ENUM = "ENUM('VVIP','VIP','CAT 1','General Admission')"
BOTH_ENUM = "ENUM('VVIP','VIP','Premium','Standard','CAT 1','General Admission')"


def main():
    conn = connect(Config)
    cur = conn.cursor()
    cur.execute("SHOW COLUMNS FROM tickets LIKE 'type'")
    col = cur.fetchone()
    if not col:
        print("The tickets table was not found. Run setup.bat (or python seed.py) first.")
        return 1
    if "Premium" not in col["Type"] and "Standard" not in col["Type"]:
        print("Already up to date: your database uses VVIP / VIP / CAT 1 / GA.")
        return 0

    print("Upgrading ticket zones...")
    cur.execute(f"ALTER TABLE tickets MODIFY type {BOTH_ENUM} NOT NULL")
    # order matters: VIP must become VVIP before Premium becomes VIP
    cur.execute("UPDATE tickets SET type='VVIP' WHERE type='VIP'")
    print(f"  VIP      -> VVIP  : {cur.rowcount} tickets")
    cur.execute("UPDATE tickets SET type='VIP' WHERE type='Premium'")
    print(f"  Premium  -> VIP   : {cur.rowcount} tickets")
    cur.execute("UPDATE tickets SET type='CAT 1' WHERE type='Standard'")
    print(f"  Standard -> CAT 1 : {cur.rowcount} tickets")
    cur.execute(f"ALTER TABLE tickets MODIFY type {NEW_ENUM} NOT NULL")
    conn.close()
    print("Done! Start the website again with run.bat.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("Upgrade failed:", exc)
        print("Check that MySQL is running and your .env settings are correct.")
        sys.exit(1)
