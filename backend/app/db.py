"""SQLite access, schema creation and seed loading."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from . import config
from .units import parse_size, product_key_for

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS chains (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'catalog',
  color TEXT,
  membership_required INTEGER NOT NULL DEFAULT 0,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS locations (
  id INTEGER PRIMARY KEY,
  chain_id INTEGER NOT NULL REFERENCES chains(id) ON DELETE CASCADE,
  external_id TEXT NOT NULL,
  name TEXT NOT NULL,
  address TEXT,
  city TEXT,
  state TEXT,
  zip TEXT,
  lat REAL,
  lng REAL,
  selected INTEGER NOT NULL DEFAULT 0,
  user_added INTEGER NOT NULL DEFAULT 0,
  UNIQUE(chain_id, external_id)
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY,
  product_key TEXT UNIQUE NOT NULL,
  brand TEXT NOT NULL,
  name TEXT NOT NULL,
  category TEXT,
  size_text TEXT,
  size_value REAL,
  size_unit TEXT,
  pack_count INTEGER NOT NULL DEFAULT 1,
  upc TEXT,
  keywords TEXT,
  image_url TEXT
);

CREATE TABLE IF NOT EXISTS offers (
  id INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  chain_id INTEGER NOT NULL REFERENCES chains(id) ON DELETE CASCADE,
  location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE,
  price REAL NOT NULL,
  sale_price REAL,
  deal_type TEXT,
  deal_text TEXT,
  deal_qty INTEGER,
  deal_price REAL,
  aisle TEXT,
  section TEXT,
  in_stock INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_offers_product ON offers(product_id);
CREATE INDEX IF NOT EXISTS idx_offers_chain ON offers(chain_id);

CREATE TABLE IF NOT EXISTS favorites (
  id INTEGER PRIMARY KEY,
  product_key TEXT UNIQUE NOT NULL,
  snapshot TEXT NOT NULL,
  times_added INTEGER NOT NULL DEFAULT 1,
  last_added TEXT,
  pinned INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lists (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  is_draft INTEGER NOT NULL DEFAULT 0,
  source_list_id INTEGER,
  created_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS list_items (
  id INTEGER PRIMARY KEY,
  list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
  product_key TEXT NOT NULL,
  offer_key TEXT NOT NULL,
  snapshot TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 1,
  checked INTEGER NOT NULL DEFAULT 0,
  added_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_list_items_list ON list_items(list_id);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY,
  chain_slug TEXT,
  program TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'rewards',
  member_id TEXT,
  username TEXT,
  notes TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS search_history (
  id INTEGER PRIMARY KEY,
  field TEXT NOT NULL,
  value TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  last_used TEXT,
  UNIQUE(field, value)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_setting(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return row["value"]


def set_setting(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


def init_db() -> None:
    """Create tables, load seed data (idempotent) and ensure a draft list exists."""
    with get_db() as conn:
        conn.executescript(SCHEMA)
        if get_setting(conn, "seed_version") != config.SEED_VERSION:
            load_seed(conn)
            set_setting(conn, "seed_version", config.SEED_VERSION)
        draft = conn.execute("SELECT id FROM lists WHERE is_draft=1").fetchone()
        if draft is None:
            conn.execute(
                "INSERT INTO lists(name, is_draft, created_at, updated_at) VALUES(?,1,?,?)",
                ("Current list", now_iso(), now_iso()),
            )


# ---------------------------------------------------------------------------
# Seed loading
# ---------------------------------------------------------------------------

def _price_for(base: float, factor: float, salt: str) -> float:
    """Deterministic, slightly jittered price so seed data looks realistic."""
    h = sum(ord(c) * (i + 1) for i, c in enumerate(salt)) % 17  # 0..16
    jitter = 1.0 + (h - 8) / 200.0  # -4% .. +4%
    p = base * factor * jitter
    # round to typical retail endings
    cents = round(p * 100)
    if cents % 100 not in (0, 25, 29, 39, 48, 49, 50, 59, 68, 69, 79, 88, 89, 97, 98, 99):
        cents = (cents // 10) * 10 + 8
    return cents / 100.0


def load_seed(conn: sqlite3.Connection) -> None:
    chains = json.loads((config.SEED_DIR / "chains.json").read_text())
    products = json.loads((config.SEED_DIR / "products.json").read_text())

    # Wipe seeded catalog (offers + products). Chains/locations are upserted so
    # user selections and user-added locations survive.
    conn.execute("DELETE FROM offers")
    conn.execute("DELETE FROM products")

    chain_ids: dict[str, int] = {}
    for c in chains:
        conn.execute(
            "INSERT INTO chains(slug, name, provider, color, membership_required, notes) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET name=excluded.name, "
            "provider=excluded.provider, color=excluded.color, "
            "membership_required=excluded.membership_required, notes=excluded.notes",
            (c["slug"], c["name"], c.get("provider", "catalog"), c.get("color"),
             1 if c.get("membership_required") else 0, c.get("notes")),
        )
        chain_id = conn.execute("SELECT id FROM chains WHERE slug=?", (c["slug"],)).fetchone()["id"]
        chain_ids[c["slug"]] = chain_id
        for loc in c.get("locations", []):
            conn.execute(
                "INSERT INTO locations(chain_id, external_id, name, address, city, state, zip, lat, lng) "
                "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(chain_id, external_id) DO UPDATE SET "
                "name=excluded.name, address=excluded.address, city=excluded.city, "
                "state=excluded.state, zip=excluded.zip",
                (chain_id, loc["id"], loc["name"], loc.get("address"), loc.get("city"),
                 loc.get("state"), loc.get("zip"), loc.get("lat"), loc.get("lng")),
            )

    factors = {c["slug"]: c.get("price_factor", 1.0) for c in chains}
    aisle_maps = {c["slug"]: c.get("aisles", {}) for c in chains}
    ts = now_iso()

    for p in products:
        size_value, size_unit, pack = parse_size(p["size"])
        key = product_key_for(p["brand"], p["name"], size_value, size_unit, pack)
        conn.execute(
            "INSERT INTO products(product_key, brand, name, category, size_text, size_value, "
            "size_unit, pack_count, upc, keywords, image_url) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (key, p["brand"], p["name"], p.get("category"), p["size"], size_value, size_unit,
             pack, p.get("upc"), " ".join(p.get("keywords", [])), p.get("image_url")),
        )
        product_id = conn.execute("SELECT id FROM products WHERE product_key=?", (key,)).fetchone()["id"]
        base = float(p["base_price"])
        for slug in p.get("stores", []):
            override = p.get("overrides", {}).get(slug, {})
            chain_id = chain_ids[slug]
            price = override.get("price", _price_for(base, factors.get(slug, 1.0), f"{key}|{slug}"))
            aisle = override.get("aisle") or aisle_maps.get(slug, {}).get(p.get("category"), "")
            section = override.get("section") or p.get("category")
            conn.execute(
                "INSERT INTO offers(product_id, chain_id, location_id, price, sale_price, deal_type, "
                "deal_text, deal_qty, deal_price, aisle, section, in_stock, updated_at) "
                "VALUES(?,?,NULL,?,?,?,?,?,?,?,?,?,?)",
                (product_id, chain_id, price, override.get("sale_price"), override.get("deal_type"),
                 override.get("deal_text"), override.get("deal_qty"), override.get("deal_price"),
                 aisle, section, 0 if override.get("out_of_stock") else 1, ts),
            )
