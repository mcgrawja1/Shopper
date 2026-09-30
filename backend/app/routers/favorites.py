from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_db, now_iso

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


class PinIn(BaseModel):
    pinned: bool


def upsert_favorite(conn, offer: dict) -> None:
    snap = {k: offer.get(k) for k in (
        "product_key", "brand", "name", "size_text", "size_value", "size_unit", "pack_count", "category",
        "upc", "image_url", "chain_slug", "chain_name", "location_id", "location_name", "effective_price",
        "unit_price", "unit_label", "provider")}
    conn.execute(
        "INSERT INTO favorites(product_key, snapshot, times_added, last_added) VALUES(?,?,1,?) "
        "ON CONFLICT(product_key) DO UPDATE SET snapshot=excluded.snapshot, times_added=times_added+1, last_added=excluded.last_added",
        (offer["product_key"], json.dumps(snap), now_iso()),
    )


@router.get("")
def list_favorites():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM favorites ORDER BY pinned DESC, times_added DESC, last_added DESC").fetchall()
    return [{**json.loads(r["snapshot"]), "id": r["id"], "product_key": r["product_key"], "times_added": r["times_added"],
             "last_added": r["last_added"], "pinned": bool(r["pinned"])} for r in rows]


@router.patch("/{fav_id}")
def pin(fav_id: int, body: PinIn):
    with get_db() as conn:
        cur = conn.execute("UPDATE favorites SET pinned=? WHERE id=?", (1 if body.pinned else 0, fav_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Unknown favorite")
    return {"ok": True}


@router.delete("/{fav_id}")
def delete(fav_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM favorites WHERE id=?", (fav_id,))
    return {"ok": True}
