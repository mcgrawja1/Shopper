from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db, get_setting
from ..providers import registry
from ..providers.registry import provider_status

router = APIRouter(prefix="/api/stores", tags=["stores"])


class LocationIn(BaseModel):
    name: str = Field(min_length=1)
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    external_id: str | None = None


class SelectIn(BaseModel):
    selected: bool


class BulkSelectIn(BaseModel):
    location_ids: list[int]
    selected: bool


def _chain_payload(conn):
    chains = conn.execute("SELECT * FROM chains ORDER BY name").fetchall()
    locs = conn.execute("SELECT * FROM locations ORDER BY name").fetchall()
    by_chain: dict[int, list] = {}
    for l in locs:
        by_chain.setdefault(l["chain_id"], []).append(dict(l))
    status = {p["slug"]: p for p in provider_status()}
    out = []
    for c in chains:
        cl = by_chain.get(c["id"], [])
        out.append({
            **dict(c),
            "membership_required": bool(c["membership_required"]),
            "live": status.get(c["provider"], {}).get("live", False),
            "provider_configured": status.get(c["provider"], {}).get("configured", True),
            "locations": cl,
            "selected_count": sum(1 for l in cl if l["selected"]),
        })
    return out


@router.get("")
def list_chains():
    with get_db() as conn:
        return {"chains": _chain_payload(conn), "providers": provider_status(),
                "home_zip": get_setting(conn, "home_zip", "")}


@router.get("/selected")
def selected():
    with get_db() as conn:
        locs = registry.selected_locations(conn)
    return [{"id": l.id, "chain_slug": l.chain_slug, "chain_name": l.chain_name, "name": l.name,
             "address": l.full_address, "provider": l.provider} for l in locs]


@router.post("/{chain_slug}/locations")
def add_location(chain_slug: str, body: LocationIn):
    with get_db() as conn:
        chain = conn.execute("SELECT id FROM chains WHERE slug=?", (chain_slug,)).fetchone()
        if not chain:
            raise HTTPException(404, "Unknown chain")
        ext = body.external_id or f"user:{body.name}|{body.address}|{body.zip}".lower()
        conn.execute(
            "INSERT INTO locations(chain_id, external_id, name, address, city, state, zip, selected, user_added) "
            "VALUES(?,?,?,?,?,?,?,1,1) ON CONFLICT(chain_id, external_id) DO UPDATE SET selected=1",
            (chain["id"], ext, body.name, body.address, body.city, body.state, body.zip),
        )
        row = conn.execute("SELECT * FROM locations WHERE chain_id=? AND external_id=?", (chain["id"], ext)).fetchone()
        return dict(row)


@router.patch("/locations/{location_id}")
def select_location(location_id: int, body: SelectIn):
    with get_db() as conn:
        cur = conn.execute("UPDATE locations SET selected=? WHERE id=?", (1 if body.selected else 0, location_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Unknown location")
    return {"ok": True}


@router.post("/locations/select")
def bulk_select(body: BulkSelectIn):
    with get_db() as conn:
        for lid in body.location_ids:
            conn.execute("UPDATE locations SET selected=? WHERE id=?", (1 if body.selected else 0, lid))
    return {"ok": True}


@router.delete("/locations/{location_id}")
def delete_location(location_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT user_added FROM locations WHERE id=?", (location_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown location")
        if not row["user_added"]:
            # built-in locations are just deselected
            conn.execute("UPDATE locations SET selected=0 WHERE id=?", (location_id,))
            return {"ok": True, "deselected": True}
        conn.execute("DELETE FROM locations WHERE id=?", (location_id,))
    return {"ok": True}


@router.post("/{chain_slug}/find")
def find_nearby(chain_slug: str, zip: str = "", radius: int = 10):
    """Look up real locations for chains backed by a live provider."""
    with get_db() as conn:
        chain = conn.execute("SELECT * FROM chains WHERE slug=?", (chain_slug,)).fetchone()
        if not chain:
            raise HTTPException(404, "Unknown chain")
        zip_code = zip or get_setting(conn, "home_zip", "")
        if not zip_code:
            raise HTTPException(400, "Enter a ZIP code (or set your home ZIP in Settings).")
        prov = registry.PROVIDERS.get(chain["provider"])
        if not prov or not prov.live:
            raise HTTPException(400, f"{chain['name']} has no live location lookup. Add your store manually.")
        try:
            found = prov.find_locations(conn, chain_slug, zip_code, radius)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Lookup failed: {e}") from e
        out = []
        for f in found:
            conn.execute(
                "INSERT INTO locations(chain_id, external_id, name, address, city, state, zip, lat, lng) "
                "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(chain_id, external_id) DO UPDATE SET name=excluded.name, "
                "address=excluded.address, city=excluded.city, state=excluded.state, zip=excluded.zip",
                (chain["id"], f["external_id"], f["name"], f["address"], f["city"], f["state"], f["zip"], f.get("lat"), f.get("lng")),
            )
            row = conn.execute("SELECT * FROM locations WHERE chain_id=? AND external_id=?", (chain["id"], f["external_id"])).fetchone()
            out.append(dict(row))
        return out
