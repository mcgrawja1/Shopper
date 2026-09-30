from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db, now_iso
from ..providers import registry
from .favorites import upsert_favorite

router = APIRouter(prefix="/api/lists", tags=["lists"])


class AddItemIn(BaseModel):
    offer: dict[str, Any]
    qty: int = Field(1, ge=1, le=99)


class ItemPatch(BaseModel):
    qty: int | None = Field(None, ge=1, le=99)
    checked: bool | None = None


class SaveIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    overwrite_id: int | None = None


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RegenIn(BaseModel):
    strategy: str = Field("cheapest", pattern="^(cheapest|same_store)$")


# ---------------------------------------------------------------------------

def _draft_id(conn) -> int:
    row = conn.execute("SELECT id FROM lists WHERE is_draft=1").fetchone()
    if row is None:
        conn.execute("INSERT INTO lists(name, is_draft, created_at, updated_at) VALUES('Current list',1,?,?)", (now_iso(), now_iso()))
        row = conn.execute("SELECT id FROM lists WHERE is_draft=1").fetchone()
    return row["id"]


def _touch(conn, list_id: int) -> None:
    conn.execute("UPDATE lists SET updated_at=? WHERE id=?", (now_iso(), list_id))


def _items(conn, list_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM list_items WHERE list_id=? ORDER BY added_at, id", (list_id,)).fetchall()
    out = []
    for r in rows:
        snap = json.loads(r["snapshot"])
        out.append({**snap, "item_id": r["id"], "qty": r["qty"], "checked": bool(r["checked"]),
                    "line_total": round(snap.get("effective_price", 0) * r["qty"], 2)})
    return out


def _breakdown(items: list[dict]) -> dict:
    stores: dict[str, dict] = {}
    for it in items:
        key = f"{it.get('chain_slug')}::{it.get('location_id')}"
        s = stores.setdefault(key, {
            "chain_slug": it.get("chain_slug"), "chain_name": it.get("chain_name"),
            "location_id": it.get("location_id"), "location_name": it.get("location_name"),
            "location_address": it.get("location_address", ""), "aisles": {}, "subtotal": 0.0, "item_count": 0,
            "deal_savings": 0.0,
        })
        aisle = it.get("aisle") or "Unknown aisle"
        a = s["aisles"].setdefault(aisle, {"aisle": aisle, "section": it.get("section", ""), "items": []})
        a["items"].append(it)
        s["subtotal"] = round(s["subtotal"] + it["line_total"], 2)
        s["item_count"] += it["qty"]
        if it.get("price") and it.get("effective_price") is not None:
            s["deal_savings"] = round(s["deal_savings"] + (it["price"] - it["effective_price"]) * it["qty"], 2)
    for s in stores.values():
        s["aisles"] = sorted(s["aisles"].values(), key=lambda a: (a["aisle"] == "Unknown aisle", _aisle_sort(a["aisle"])))
    store_list = sorted(stores.values(), key=lambda s: (s["chain_name"] or "", s["location_name"] or ""))
    return {
        "stores": store_list,
        "total": round(sum(s["subtotal"] for s in store_list), 2),
        "item_count": sum(s["item_count"] for s in store_list),
        "deal_savings": round(sum(s["deal_savings"] for s in store_list), 2),
        "store_count": len(store_list),
    }


def _aisle_sort(a: str):
    import re
    m = re.search(r"(\d+)", a or "")
    return (int(m.group(1)) if m else 9999, a)


def _payload(conn, list_id: int) -> dict:
    row = conn.execute("SELECT * FROM lists WHERE id=?", (list_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Unknown list")
    items = _items(conn, list_id)
    return {**dict(row), "is_draft": bool(row["is_draft"]), "items": items, "breakdown": _breakdown(items)}


# -- draft ("current") list --------------------------------------------------

@router.get("/current")
def get_current():
    with get_db() as conn:
        return _payload(conn, _draft_id(conn))


@router.post("/current/items")
def add_item(body: AddItemIn):
    offer = body.offer
    if not offer.get("offer_key") or not offer.get("product_key"):
        raise HTTPException(400, "Offer is missing keys")
    with get_db() as conn:
        lid = _draft_id(conn)
        existing = conn.execute("SELECT id, qty FROM list_items WHERE list_id=? AND offer_key=?", (lid, offer["offer_key"])).fetchone()
        if existing:
            conn.execute("UPDATE list_items SET qty=qty+?, snapshot=? WHERE id=?", (body.qty, json.dumps(offer), existing["id"]))
        else:
            conn.execute(
                "INSERT INTO list_items(list_id, product_key, offer_key, snapshot, qty, added_at) VALUES(?,?,?,?,?,?)",
                (lid, offer["product_key"], offer["offer_key"], json.dumps(offer), body.qty, now_iso()),
            )
        upsert_favorite(conn, offer)
        _touch(conn, lid)
        return _payload(conn, lid)


@router.patch("/current/items/{item_id}")
def patch_item(item_id: int, body: ItemPatch):
    with get_db() as conn:
        lid = _draft_id(conn)
        if body.qty is not None:
            conn.execute("UPDATE list_items SET qty=? WHERE id=? AND list_id=?", (body.qty, item_id, lid))
        if body.checked is not None:
            conn.execute("UPDATE list_items SET checked=? WHERE id=? AND list_id=?", (1 if body.checked else 0, item_id, lid))
        _touch(conn, lid)
        return _payload(conn, lid)


@router.delete("/current/items/{item_id}")
def delete_item(item_id: int):
    with get_db() as conn:
        lid = _draft_id(conn)
        conn.execute("DELETE FROM list_items WHERE id=? AND list_id=?", (item_id, lid))
        _touch(conn, lid)
        return _payload(conn, lid)


@router.delete("/current")
def clear_current():
    with get_db() as conn:
        lid = _draft_id(conn)
        conn.execute("DELETE FROM list_items WHERE list_id=?", (lid,))
        conn.execute("UPDATE lists SET source_list_id=NULL, name='Current list' WHERE id=?", (lid,))
        _touch(conn, lid)
        return _payload(conn, lid)


@router.post("/current/save")
def save_current(body: SaveIn):
    """Snapshot the draft into a named saved list (or overwrite an existing one)."""
    with get_db() as conn:
        lid = _draft_id(conn)
        if body.overwrite_id:
            target = conn.execute("SELECT id FROM lists WHERE id=? AND is_draft=0", (body.overwrite_id,)).fetchone()
            if not target:
                raise HTTPException(404, "Unknown saved list")
            tid = target["id"]
            conn.execute("DELETE FROM list_items WHERE list_id=?", (tid,))
            conn.execute("UPDATE lists SET name=?, updated_at=? WHERE id=?", (body.name, now_iso(), tid))
        else:
            conn.execute("INSERT INTO lists(name, is_draft, created_at, updated_at) VALUES(?,0,?,?)", (body.name, now_iso(), now_iso()))
            tid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        conn.execute(
            "INSERT INTO list_items(list_id, product_key, offer_key, snapshot, qty, checked, added_at) "
            "SELECT ?, product_key, offer_key, snapshot, qty, 0, added_at FROM list_items WHERE list_id=?",
            (tid, lid),
        )
        conn.execute("UPDATE lists SET source_list_id=?, name=? WHERE id=?", (tid, body.name, lid))
        return _payload(conn, tid)


@router.post("/current/regenerate")
def regenerate_current(body: RegenIn):
    """Re-price every item against the currently selected stores."""
    with get_db() as conn:
        lid = _draft_id(conn)
        return _regenerate(conn, lid, body.strategy)


def _regenerate(conn, lid: int, strategy: str) -> dict:
    locs = registry.selected_locations(conn)
    rows = conn.execute("SELECT * FROM list_items WHERE list_id=?", (lid,)).fetchall()
    changes = []
    for r in rows:
        snap = json.loads(r["snapshot"])
        offers, _ = registry.lookup(conn, r["product_key"], locs)
        if not offers:
            changes.append({"item_id": r["id"], "name": snap.get("name"), "status": "unavailable"})
            continue
        offers = [o for o in offers if o["in_stock"]] or offers
        if strategy == "same_store":
            same = [o for o in offers if o["location_id"] == snap.get("location_id")]
            best = same[0] if same else min(offers, key=lambda o: o["effective_price"])
        else:
            best = min(offers, key=lambda o: (o["unit_price"] if o["unit_price"] is not None else 1e9, o["effective_price"]))
        old_price = snap.get("effective_price")
        conn.execute("UPDATE list_items SET offer_key=?, snapshot=? WHERE id=?", (best["offer_key"], json.dumps(best), r["id"]))
        changes.append({
            "item_id": r["id"], "name": best["name"], "status": "updated",
            "old_price": old_price, "new_price": best["effective_price"],
            "old_store": snap.get("chain_name"), "new_store": best["chain_name"],
            "moved": best["location_id"] != snap.get("location_id"),
        })
    _touch(conn, lid)
    payload = _payload(conn, lid)
    payload["changes"] = changes
    return payload


# -- saved lists -------------------------------------------------------------

@router.get("")
def list_saved():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT l.*, COUNT(i.id) AS item_count, COALESCE(SUM(i.qty),0) AS qty FROM lists l "
            "LEFT JOIN list_items i ON i.list_id=l.id WHERE l.is_draft=0 GROUP BY l.id ORDER BY l.updated_at DESC"
        ).fetchall()
        out = []
        for r in rows:
            items = _items(conn, r["id"])
            out.append({**dict(r), "is_draft": False, "total": round(sum(i["line_total"] for i in items), 2),
                        "stores": sorted({i.get("chain_name") or "" for i in items})})
        return out


@router.get("/{list_id}")
def get_saved(list_id: int):
    with get_db() as conn:
        return _payload(conn, list_id)


@router.post("/{list_id}/load")
def load_saved(list_id: int, regenerate: bool = False, strategy: str = "cheapest"):
    """Copy a saved list into the draft (replacing it). Optionally re-price."""
    with get_db() as conn:
        src = conn.execute("SELECT * FROM lists WHERE id=? AND is_draft=0", (list_id,)).fetchone()
        if not src:
            raise HTTPException(404, "Unknown saved list")
        lid = _draft_id(conn)
        conn.execute("DELETE FROM list_items WHERE list_id=?", (lid,))
        conn.execute(
            "INSERT INTO list_items(list_id, product_key, offer_key, snapshot, qty, checked, added_at) "
            "SELECT ?, product_key, offer_key, snapshot, qty, 0, added_at FROM list_items WHERE list_id=?",
            (lid, list_id),
        )
        conn.execute("UPDATE lists SET source_list_id=?, name=?, updated_at=? WHERE id=?", (list_id, src["name"], now_iso(), lid))
        if regenerate:
            return _regenerate(conn, lid, strategy if strategy in ("cheapest", "same_store") else "cheapest")
        return _payload(conn, lid)


@router.patch("/{list_id}")
def rename(list_id: int, body: RenameIn):
    with get_db() as conn:
        cur = conn.execute("UPDATE lists SET name=?, updated_at=? WHERE id=? AND is_draft=0", (body.name, now_iso(), list_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Unknown saved list")
        return _payload(conn, list_id)


@router.delete("/{list_id}")
def delete_saved(list_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM lists WHERE id=? AND is_draft=0", (list_id,))
        conn.execute("UPDATE lists SET source_list_id=NULL WHERE source_list_id=?", (list_id,))
    return {"ok": True}
