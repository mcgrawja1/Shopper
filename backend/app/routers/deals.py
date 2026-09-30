"""Phase 2: deal discovery. Surfaces sales / BOGO / multi-buy offers for
products on the current list, and a general 'deals at my stores' feed."""
from __future__ import annotations

import json

from fastapi import APIRouter

from ..db import get_db
from ..providers import registry
from ..providers.base import Location, build_offer

router = APIRouter(prefix="/api/deals", tags=["deals"])


def _catalog_deals(conn, locs: list[Location], limit: int = 40) -> list[dict]:
    locs = [l for l in locs if l.provider == "catalog"]
    if not locs:
        return []
    chain_ids = sorted({l.chain_id for l in locs})
    rows = conn.execute(
        "SELECT o.*, p.product_key, p.brand, p.name, p.category, p.size_text, p.size_value, p.size_unit, "
        "p.pack_count, p.upc, p.image_url FROM offers o JOIN products p ON p.id=o.product_id "
        f"WHERE (o.deal_type IS NOT NULL OR o.sale_price IS NOT NULL) AND o.chain_id IN ({','.join('?' * len(chain_ids))})",
        chain_ids,
    ).fetchall()
    out = []
    for r in rows:
        for loc in locs:
            if loc.chain_id != r["chain_id"]:
                continue
            if r["location_id"] and r["location_id"] != loc.id:
                continue
            out.append(build_offer(
                offer_key=f"catalog:{r['id']}:{loc.id}", provider="catalog", product_key=r["product_key"],
                brand=r["brand"], name=r["name"], size_value=r["size_value"], size_unit=r["size_unit"],
                pack_count=r["pack_count"], category=r["category"], upc=r["upc"], image_url=r["image_url"],
                loc=loc, price=r["price"], sale_price=r["sale_price"], deal_type=r["deal_type"],
                deal_text=r["deal_text"], deal_qty=r["deal_qty"], deal_price=r["deal_price"], aisle=r["aisle"],
                section=r["section"], in_stock=bool(r["in_stock"]), updated_at=r["updated_at"], size_text=r["size_text"],
            ))
    for o in out:
        o["savings"] = round(o["price"] - o["effective_price"], 2)
        o["savings_pct"] = round(100 * o["savings"] / o["price"]) if o["price"] else 0
    out.sort(key=lambda o: -o["savings_pct"])
    return out[:limit]


@router.get("")
def deals_feed():
    with get_db() as conn:
        locs = registry.selected_locations(conn)
        return {"deals": _catalog_deals(conn, locs)}


@router.get("/for-list")
def deals_for_list():
    """For each item on the current list, find a deal on the same product (any
    selected store) that beats what the list currently has."""
    with get_db() as conn:
        locs = registry.selected_locations(conn)
        draft = conn.execute("SELECT id FROM lists WHERE is_draft=1").fetchone()
        if not draft:
            return {"recommendations": []}
        rows = conn.execute("SELECT * FROM list_items WHERE list_id=?", (draft["id"],)).fetchall()
        recs = []
        for r in rows:
            snap = json.loads(r["snapshot"])
            offers, _ = registry.lookup(conn, r["product_key"], locs)
            deals = [o for o in offers if o["deal"] and o["in_stock"]]
            if not deals:
                continue
            best = min(deals, key=lambda o: o["effective_price"])
            current = snap.get("effective_price") or 0
            if best["offer_key"] == r["offer_key"] or best["effective_price"] >= current:
                continue
            recs.append({
                "item_id": r["id"], "current": snap, "deal": best,
                "savings_each": round(current - best["effective_price"], 2),
                "savings_total": round((current - best["effective_price"]) * r["qty"], 2),
                "qty": r["qty"],
            })
        recs.sort(key=lambda x: -x["savings_total"])
        return {"recommendations": recs}
