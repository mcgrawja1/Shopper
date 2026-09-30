"""Provider registry + the search orchestrator used by the API."""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from .base import Location, Provider, SearchQuery
from .catalog import CatalogProvider
from .kroger import KrogerProvider

catalog = CatalogProvider()
kroger = KrogerProvider()
PROVIDERS: dict[str, Provider] = {catalog.slug: catalog, kroger.slug: kroger}


def provider_status() -> list[dict]:
    return [
        {"slug": "catalog", "name": "Local catalog", "live": False, "configured": True,
         "description": "Built-in sample catalog for every chain. Prices are illustrative until a live provider is connected."},
        {"slug": "kroger", "name": "Kroger family (live)", "live": True, "configured": kroger.configured,
         "description": "Real prices, aisle locations and sales from the Kroger Products API."},
    ]


def selected_locations(conn, only_ids: list[int] | None = None) -> list[Location]:
    sql = (
        "SELECT l.*, c.slug AS chain_slug, c.name AS chain_name, c.provider AS provider "
        "FROM locations l JOIN chains c ON c.id=l.chain_id WHERE l.selected=1"
    )
    params: list = []
    if only_ids:
        sql += f" AND l.id IN ({','.join('?' * len(only_ids))})"
        params = list(only_ids)
    sql += " ORDER BY c.name, l.name"
    return [Location(
        id=r["id"], chain_id=r["chain_id"], chain_slug=r["chain_slug"], chain_name=r["chain_name"],
        external_id=r["external_id"], name=r["name"], address=r["address"] or "", city=r["city"] or "",
        state=r["state"] or "", zip=r["zip"] or "", provider=r["provider"] or "catalog",
    ) for r in conn.execute(sql, params).fetchall()]


def _run(fn_name: str, conn, arg, locations: list[Location]) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    offers: list[dict] = []
    by_provider: dict[str, list[Location]] = defaultdict(list)
    for loc in locations:
        by_provider[loc.provider].append(loc)
    jobs = []
    fallback: list[Location] = []
    for pslug, locs in by_provider.items():
        prov = PROVIDERS.get(pslug)
        if prov is None or (pslug == "kroger" and not kroger.configured):
            # No live provider available: fall back to sample catalog prices.
            if pslug == "kroger":
                warnings.append("Kroger is showing sample catalog prices. Add KROGER_CLIENT_ID / KROGER_CLIENT_SECRET for live prices.")
            fallback.extend(replace(l, provider="catalog") for l in locs)
            continue
        jobs.append((prov, locs))
    if fallback:
        for i, (prov, locs) in enumerate(jobs):
            if prov is catalog:
                jobs[i] = (prov, locs + fallback)
                break
        else:
            jobs.append((catalog, fallback))
    if not jobs:
        return offers, warnings
    with ThreadPoolExecutor(max_workers=max(1, len(jobs))) as ex:
        futures = [ex.submit(getattr(prov, fn_name), conn, arg, locs) for prov, locs in jobs]
        for f in futures:
            try:
                offers.extend(f.result())
            except Exception as e:  # noqa: BLE001
                warnings.append(f"Provider error: {e}")
    return offers, warnings


def search(conn, query: SearchQuery, locations: list[Location]) -> tuple[list[dict], list[str]]:
    return _run("search", conn, query, locations)


def lookup(conn, product_key: str, locations: list[Location]) -> tuple[list[dict], list[str]]:
    return _run("lookup", conn, product_key, locations)


def group_offers(offers: list[dict], sort: str = "unit_price") -> list[dict]:
    """Group flat offers by product; sort groups and their offers."""
    groups: dict[str, dict] = {}
    for o in offers:
        g = groups.setdefault(o["product_key"], {
            "product_key": o["product_key"], "brand": o["brand"], "name": o["name"],
            "size_text": o["size_text"], "size_value": o["size_value"], "size_unit": o["size_unit"],
            "pack_count": o["pack_count"], "category": o["category"], "upc": o["upc"],
            "image_url": o["image_url"], "unit_label": o["unit_label"], "score": o["score"], "offers": [],
        })
        g["offers"].append(o)
        g["score"] = max(g["score"], o["score"])
    keyfn = _offer_sort_key(sort)
    for g in groups.values():
        g["offers"].sort(key=keyfn)
        g["best"] = g["offers"][0]
        g["price_range"] = [min(o["effective_price"] for o in g["offers"]),
                            max(o["effective_price"] for o in g["offers"])]
        g["has_deal"] = any(o["deal"] for o in g["offers"])
    out = list(groups.values())
    if sort == "relevance":
        out.sort(key=lambda g: (-g["score"], keyfn(g["best"])))
    else:
        out.sort(key=lambda g: keyfn(g["best"]))
    return out


def _offer_sort_key(sort: str):
    big = 1e9
    if sort == "price":
        return lambda o: (0 if o["in_stock"] else 1, o["effective_price"])
    if sort == "store":
        return lambda o: (o["chain_name"], o["location_name"], o["effective_price"])
    if sort == "relevance":
        return lambda o: (-o["score"], o["unit_price"] if o["unit_price"] is not None else big)
    # default: unit price, out-of-stock last, unknown unit last
    return lambda o: (0 if o["in_stock"] else 1, o["unit_price"] if o["unit_price"] is not None else big,
                      o["effective_price"])
