from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import get_db, now_iso
from ..providers import registry
from ..providers.base import SearchQuery
from ..providers.registry import catalog

router = APIRouter(prefix="/api", tags=["search"])


def _remember(conn, field: str, value: str) -> None:
    value = (value or "").strip()
    if not value:
        return
    conn.execute(
        "INSERT INTO search_history(field, value, count, last_used) VALUES(?,?,1,?) "
        "ON CONFLICT(field, value) DO UPDATE SET count=count+1, last_used=excluded.last_used",
        (field, value, now_iso()),
    )


@router.get("/search")
def search(
    brand: str = "", item: str = "", size: str = "", category: str = "", upc: str = "",
    sort: str = Query("unit_price", pattern="^(unit_price|price|store|relevance)$"),
    locations: str = "", in_stock_only: bool = False,
):
    q = SearchQuery(brand=brand.strip(), item=item.strip(), size=size.strip(), category=category.strip(), upc=upc.strip())
    if q.is_empty():
        return {"query": q.__dict__, "groups": [], "offers": [], "variants": [], "stores_searched": [], "warnings": ["Enter a brand, item or size to search."]}
    only_ids = [int(x) for x in locations.split(",") if x.strip().isdigit()] if locations else None
    with get_db() as conn:
        locs = registry.selected_locations(conn, only_ids)
        warnings: list[str] = []
        if not locs:
            warnings.append("No store locations selected. Pick your stores on the Stores page.")
        offers, w = registry.search(conn, q, locs)
        warnings.extend(w)
        if in_stock_only:
            offers = [o for o in offers if o["in_stock"]]
        for f, v in (("brand", brand), ("item", item), ("size", size), ("category", category)):
            _remember(conn, f, v)
    groups = registry.group_offers(offers, sort)
    variants: dict[str, int] = {}
    for g in groups:
        if g["size_text"]:
            variants[g["size_text"]] = variants.get(g["size_text"], 0) + 1
    flat = [o for g in groups for o in g["offers"]]
    flat.sort(key=registry._offer_sort_key(sort))
    return {
        "query": q.__dict__,
        "groups": groups,
        "offers": flat,
        "variants": [{"size_text": k, "count": v} for k, v in sorted(variants.items())],
        "stores_searched": [{"location_id": l.id, "chain": l.chain_name, "name": l.name, "provider": l.provider} for l in locs],
        "warnings": warnings,
    }


@router.get("/autocomplete")
def autocomplete(field: str = Query(..., pattern="^(brand|item|size|category)$"), q: str = "", limit: int = 10):
    with get_db() as conn:
        base = catalog.suggest(conn, field, q, limit)
        hist_rows = conn.execute(
            "SELECT value FROM search_history WHERE field=? AND lower(value) LIKE ? ORDER BY count DESC, last_used DESC LIMIT ?",
            (field, f"{q.lower()}%", limit),
        ).fetchall()
    hist = [r["value"] for r in hist_rows]
    seen, out = set(), []
    for v in hist + base:
        k = v.lower()
        if k not in seen:
            seen.add(k)
            out.append({"value": v, "source": "history" if v in hist else "catalog"})
    return out[:limit]


@router.get("/lookup")
def lookup(product_key: str, sort: str = Query("unit_price", pattern="^(unit_price|price|store|relevance)$")):
    """Re-price a known product (from favorites or a saved list) at the selected stores."""
    with get_db() as conn:
        locs = registry.selected_locations(conn)
        offers, warnings = registry.lookup(conn, product_key, locs)
    offers.sort(key=registry._offer_sort_key(sort))
    return {"offers": offers, "warnings": warnings}
