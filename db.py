"""Tiny MySQL helper built on PyMySQL.

    rows = query("SELECT * FROM concerts WHERE city=%s", (city,))
    row  = query("SELECT * FROM users WHERE id=%s", (uid,), one=True)
    new_id = execute("INSERT INTO artists (name, genre) VALUES (%s,%s)", (n, g))

    with transaction() as cur:          # all-or-nothing block
        cur.execute(...)
"""
from contextlib import contextmanager

import pymysql
from flask import current_app, g


def connect(cfg):
    """Open a new connection from a config object / dict-like."""
    get = cfg.get if isinstance(cfg, dict) else lambda k: getattr(cfg, k)
    return pymysql.connect(
        host=get("DB_HOST"),
        port=int(get("DB_PORT")),
        user=get("DB_USER"),
        password=get("DB_PASSWORD"),
        database=get("DB_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config)
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=None, one=False):
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        rows = cur.fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def scalar(sql, args=None, default=0):
    row = query(sql, args, one=True)
    if not row:
        return default
    value = list(row.values())[0]
    return default if value is None else value


def execute(sql, args=None):
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid


@contextmanager
def transaction():
    conn = get_db()
    conn.begin()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def init_app(app):
    app.teardown_appcontext(close_db)
