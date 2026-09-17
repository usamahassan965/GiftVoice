"""SQLite storage: products, carts, orders, returns, recipient profiles, tickets.

Plain sqlite3 keeps the project dependency-light and the DB a single file.
JSON columns hold list/dict fields.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app import config

_db_path: Path = config.DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    category        TEXT NOT NULL,
    price           REAL NOT NULL,
    image_path      TEXT,
    image_credit    TEXT,
    image_credit_url TEXT,
    tags            TEXT NOT NULL DEFAULT '[]',
    interests       TEXT NOT NULL DEFAULT '[]',
    occasions       TEXT NOT NULL DEFAULT '[]',
    recipients      TEXT NOT NULL DEFAULT '[]',
    stock           INTEGER NOT NULL DEFAULT 0,
    ship_days       INTEGER NOT NULL DEFAULT 3,
    rating          REAL NOT NULL DEFAULT 4.0,
    review_count    INTEGER NOT NULL DEFAULT 0,
    reviews         TEXT NOT NULL DEFAULT '[]',
    source          TEXT NOT NULL DEFAULT 'curated'
);

CREATE TABLE IF NOT EXISTS cart_items (
    session_id  TEXT NOT NULL,
    product_id  TEXT NOT NULL REFERENCES products(id),
    qty         INTEGER NOT NULL,
    PRIMARY KEY (session_id, product_id)
);

CREATE TABLE IF NOT EXISTS gift_options (
    session_id      TEXT PRIMARY KEY,
    wrap            TEXT,            -- NULL | classic | premium | eco
    message         TEXT,
    hide_price      INTEGER NOT NULL DEFAULT 0,
    recipient_name  TEXT,
    ship_address    TEXT,
    ship_city       TEXT,
    express         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    customer_id     TEXT NOT NULL,
    items           TEXT NOT NULL,   -- [{product_id, name, price, qty}]
    subtotal        REAL NOT NULL,
    gift_fee        REAL NOT NULL,
    shipping_fee    REAL NOT NULL,
    total           REAL NOT NULL,
    gift            TEXT NOT NULL,   -- gift_options snapshot
    recipient_id    TEXT,
    status          TEXT NOT NULL,   -- pending_payment | paid | shipped | delivered | return_requested
    created_at      TEXT NOT NULL,
    eta             TEXT NOT NULL,
    payment_url     TEXT
);

CREATE TABLE IF NOT EXISTS returns (
    id          TEXT PRIMARY KEY,
    order_id    TEXT NOT NULL REFERENCES orders(id),
    reason      TEXT NOT NULL,
    resolution  TEXT NOT NULL,       -- refund | exchange
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipients (
    id              TEXT PRIMARY KEY,
    customer_id     TEXT NOT NULL,
    name            TEXT NOT NULL,
    relationship    TEXT,
    interests       TEXT NOT NULL DEFAULT '[]',
    notes           TEXT,
    occasions       TEXT NOT NULL DEFAULT '[]',   -- [{type, date: MM-DD}]
    updated_at      TEXT NOT NULL,
    UNIQUE (customer_id, name)
);

CREATE TABLE IF NOT EXISTS gift_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     TEXT NOT NULL,
    recipient_id    TEXT NOT NULL REFERENCES recipients(id),
    product_id      TEXT NOT NULL,
    order_id        TEXT NOT NULL,
    occasion        TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    reason      TEXT NOT NULL,
    summary     TEXT,
    created_at  TEXT NOT NULL
);
"""

JSON_COLUMNS = {"tags", "interests", "occasions", "recipients", "reviews", "items", "gift"}


def db_path() -> Path:
    return _db_path


def set_db_path(path: Path | str) -> None:
    """Point the app at a different DB file (used by tests)."""
    global _db_path
    _db_path = Path(path)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for key in JSON_COLUMNS & out.keys():
        if isinstance(out[key], str):
            out[key] = json.loads(out[key])
    return out


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
