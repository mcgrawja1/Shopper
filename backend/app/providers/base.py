"""Provider interface. A provider turns a search query + a set of selected
store locations into a list of normalised offers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..units import effective_price, format_size, unit_price


@dataclass
class SearchQuery:
    brand: str = ""
    item: str = ""
    size: str = ""
    category: str = ""
    upc: str = ""

    @property
    def text(self) -> str:
        return " ".join(x for x in (self.brand, self.item, self.size) if x).strip()

    def is_empty(self) -> bool:
        return not (self.brand or self.item or self.size or self.upc)


@dataclass
class Location:
    id: int
    chain_id: int
    chain_slug: str
    chain_name: str
    external_id: str
    name: str
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    provider: str = "catalog"

    @property
    def full_address(self) -> str:
        parts = [self.address, ", ".join(x for x in (self.city, self.state) if x), self.zip]
        return " ".join(p for p in parts if p).strip()


def build_offer(*, offer_key: str, provider: str, product_key: str, brand: str, name: str,
                size_value, size_unit, pack_count: int, category: str, upc: str,
                image_url: Optional[str], loc: Location, price: float, sale_price=None,
                deal_type=None, deal_text=None, deal_qty=None, deal_price=None,
                aisle: str = "", section: str = "", in_stock: bool = True,
                updated_at: Optional[str] = None, score: float = 0.0,
                size_text: Optional[str] = None) -> dict[str, Any]:
    eff = effective_price(price, sale_price, deal_type, deal_qty, deal_price)
    up = unit_price(eff, size_value, size_unit, pack_count)
    deal = None
    if deal_type or sale_price:
        deal = {
            "type": deal_type or "sale",
            "text": deal_text or (f"Sale: ${sale_price:.2f}" if sale_price else ""),
            "qty": deal_qty,
            "price": deal_price,
        }
    return {
        "offer_key": offer_key,
        "provider": provider,
        "product_key": product_key,
        "brand": brand,
        "name": name,
        "size_text": size_text or format_size(size_value, size_unit, pack_count),
        "size_value": size_value,
        "size_unit": size_unit,
        "pack_count": pack_count or 1,
        "category": category or "",
        "upc": upc or "",
        "image_url": image_url,
        "chain_slug": loc.chain_slug,
        "chain_name": loc.chain_name,
        "location_id": loc.id,
        "location_name": loc.name,
        "location_address": loc.full_address,
        "price": round(price, 2),
        "sale_price": round(sale_price, 2) if sale_price else None,
        "effective_price": eff,
        "aisle": aisle or "",
        "section": section or "",
        "in_stock": bool(in_stock),
        "deal": deal,
        "updated_at": updated_at,
        "score": round(score, 3),
        **up,
    }


class Provider:
    slug = "base"
    live = False

    def search(self, conn, query: SearchQuery, locations: list[Location]) -> list[dict]:
        raise NotImplementedError

    def lookup(self, conn, product_key: str, locations: list[Location]) -> list[dict]:
        """Re-price a known product at the given locations (list regeneration)."""
        raise NotImplementedError

    def find_locations(self, conn, chain_slug: str, zip_code: str, radius_miles: int = 10) -> list[dict]:
        return []
