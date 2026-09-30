"""Local catalog provider: prices stored in SQLite (seed data + anything the
user imports). Chain-level offers apply to every location of that chain
unless a location-specific offer row exists."""
from __future__ import annotations

import difflib
import re
from collections import defaultdict

from ..units import parse_size, family_of
from .base import Location, Provider, SearchQuery, build_offer

STOPWORDS = {"the", "a", "an", "of", "and", "&", "with", "for", "in", "pack", "pk", "ct", "count"}
_token_re = re.compile(r"[a-z0-9']+")


def tokens(s: str) -> list[str]:
    return [t for t in _token_re.findall((s or "").lower()) if t not in STOPWORDS]


def _match_token(tok: str, hay: list[str]) -> float:
    if tok in hay:
        return 2.0
    for h in hay:
        if h.startswith(tok) or tok.startswith(h) and len(h) >= 3:
            return 1.5
    if len(tok) >= 4:
        close = difflib.get_close_matches(tok, hay, n=1, cutoff=0.8)
        if close:
            return 1.0
    return 0.0


def score_product(p, q: SearchQuery) -> float:
    """0 = no match. Higher is better."""
    name_toks = tokens(p["name"])
    brand_toks = tokens(p["brand"])
    kw_toks = tokens(p["keywords"] or "")
    cat_toks = tokens(p["category"] or "")
    hay = name_toks + brand_toks + kw_toks + cat_toks

    score = 0.0
    item_toks = tokens(q.item)
    if item_toks:
        matched = 0
        for t in item_toks:
            s = _match_token(t, hay)
            if s:
                matched += 1
                score += s * (1.5 if t in name_toks else 1.0)
        if matched / len(item_toks) < 0.6:
            return 0.0
    brand_q = tokens(q.brand)
    if brand_q:
        bscore = sum(_match_token(t, brand_toks) for t in brand_q)
        if bscore == 0:
            # brand given but doesn't match -> only keep if item matched strongly
            if not item_toks:
                return 0.0
            score -= 2.0
        else:
            score += bscore * 2
    if not item_toks and not brand_q:
        return 0.0
    if q.category and (p["category"] or "").lower() != q.category.lower():
        return 0.0
    if q.size:
        sv, su, pk = parse_size(q.size)
        if sv and p["size_value"]:
            same_fam = family_of(su) == family_of(p["size_unit"])
            if same_fam and abs(float(p["size_value"]) - sv) < 0.01 and (pk == 1 or pk == p["pack_count"]):
                score += 3.0
            elif family_of(su) == "count" and pk == 1 and int(sv) == (p["pack_count"] or 1) and sv > 1:
                score += 3.0  # "5 pack" / "12 ct" matched the pack count
            elif same_fam:
                score += 0.5
            else:
                score -= 0.5
    return score


def _load_locations_by_chain(locations: list[Location]) -> dict[int, list[Location]]:
    by_chain: dict[int, list[Location]] = defaultdict(list)
    for loc in locations:
        by_chain[loc.chain_id].append(loc)
    return by_chain


class CatalogProvider(Provider):
    slug = "catalog"
    live = False

    def _offers_for_products(self, conn, product_rows, locations, scores):
        by_chain = _load_locations_by_chain(locations)
        if not by_chain or not product_rows:
            return []
        ids = [p["id"] for p in product_rows]
        chain_ids = list(by_chain.keys())
        q = (
            "SELECT o.*, p.product_key, p.brand, p.name, p.category, p.size_text, p.size_value, "
            "p.size_unit, p.pack_count, p.upc, p.image_url FROM offers o JOIN products p ON p.id=o.product_id "
            f"WHERE o.product_id IN ({','.join('?' * len(ids))}) AND o.chain_id IN ({','.join('?' * len(chain_ids))})"
        )
        rows = conn.execute(q, ids + chain_ids).fetchall()
        # location-specific rows override chain-level rows
        specific = {(r["product_id"], r["location_id"]): r for r in rows if r["location_id"]}
        chain_level = {(r["product_id"], r["chain_id"]): r for r in rows if not r["location_id"]}
        out = []
        for pid in ids:
            for chain_id, locs in by_chain.items():
                for loc in locs:
                    r = specific.get((pid, loc.id)) or chain_level.get((pid, chain_id))
                    if r is None:
                        continue
                    out.append(build_offer(
                        offer_key=f"catalog:{r['id']}:{loc.id}", provider="catalog",
                        product_key=r["product_key"], brand=r["brand"], name=r["name"],
                        size_value=r["size_value"], size_unit=r["size_unit"], pack_count=r["pack_count"],
                        category=r["category"], upc=r["upc"], image_url=r["image_url"], loc=loc,
                        price=r["price"], sale_price=r["sale_price"], deal_type=r["deal_type"],
                        deal_text=r["deal_text"], deal_qty=r["deal_qty"], deal_price=r["deal_price"],
                        aisle=r["aisle"], section=r["section"], in_stock=bool(r["in_stock"]),
                        updated_at=r["updated_at"], score=scores.get(pid, 0.0), size_text=r["size_text"],
                    ))
        return out

    def search(self, conn, query: SearchQuery, locations: list[Location]) -> list[dict]:
        locations = [l for l in locations if l.provider == "catalog"]
        if not locations:
            return []
        if query.upc:
            rows = conn.execute("SELECT * FROM products WHERE upc=?", (query.upc,)).fetchall()
            return self._offers_for_products(conn, rows, locations, {r["id"]: 10.0 for r in rows})
        rows = conn.execute("SELECT * FROM products").fetchall()
        scored = [(score_product(r, query), r) for r in rows]
        scored = [(s, r) for s, r in scored if s > 0]
        scored.sort(key=lambda x: -x[0])
        scored = scored[:60]
        return self._offers_for_products(conn, [r for _, r in scored], locations, {r["id"]: s for s, r in scored})

    def lookup(self, conn, product_key: str, locations: list[Location]) -> list[dict]:
        locations = [l for l in locations if l.provider == "catalog"]
        rows = conn.execute("SELECT * FROM products WHERE product_key=?", (product_key,)).fetchall()
        return self._offers_for_products(conn, rows, locations, {r["id"]: 10.0 for r in rows})

    # -- autocomplete helpers -------------------------------------------------
    def suggest(self, conn, field: str, q: str, limit: int = 10) -> list[str]:
        q = (q or "").strip().lower()
        col = {"brand": "brand", "item": "name", "size": "size_text", "category": "category"}.get(field)
        if not col:
            return []
        rows = conn.execute(f"SELECT DISTINCT {col} AS v FROM products WHERE {col} IS NOT NULL AND {col} != ''").fetchall()
        vals = [r["v"] for r in rows]
        if not q:
            return sorted(vals, key=str.lower)[:limit]
        starts = [v for v in vals if v.lower().startswith(q)]
        contains = [v for v in vals if q in v.lower() and v not in starts]
        fuzzy = []
        if len(q) >= 3:
            fuzzy = [v for v in difflib.get_close_matches(q, [v.lower() for v in vals], n=limit, cutoff=0.6)]
            fuzzy = [v for v in vals if v.lower() in fuzzy and v not in starts and v not in contains]
        return (sorted(starts, key=str.lower) + sorted(contains, key=str.lower) + fuzzy)[:limit]
