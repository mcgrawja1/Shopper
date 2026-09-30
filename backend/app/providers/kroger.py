"""Live Kroger Products API adapter (Kroger, Fred Meyer, Ralphs, King Soopers,
Fry's, Harris Teeter, Smith's, QFC, Dillons, Mariano's, ...).

Requires KROGER_CLIENT_ID / KROGER_CLIENT_SECRET from https://developer.kroger.com.
Without credentials the provider is inactive and Kroger locations cannot be
searched live."""
from __future__ import annotations

import base64
import logging
import time
from typing import Optional

import httpx

from .. import config
from ..units import parse_size, product_key_for
from .base import Location, Provider, SearchQuery, build_offer

log = logging.getLogger(__name__)


class KrogerProvider(Provider):
    slug = "kroger"
    live = True

    def __init__(self):
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(config.KROGER_CLIENT_ID and config.KROGER_CLIENT_SECRET)

    # -- auth ------------------------------------------------------------------
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        creds = base64.b64encode(f"{config.KROGER_CLIENT_ID}:{config.KROGER_CLIENT_SECRET}".encode()).decode()
        r = httpx.post(
            f"{config.KROGER_BASE_URL}/connect/oauth2/token",
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": "product.compact"},
            timeout=15,
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 1800))
        return self._token

    def _get(self, path: str, params: dict) -> dict:
        r = httpx.get(
            f"{config.KROGER_BASE_URL}{path}", params=params,
            headers={"Authorization": f"Bearer {self._get_token()}", "Accept": "application/json"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    # -- locations ----------------------------------------------------------------
    def find_locations(self, conn, chain_slug: str, zip_code: str, radius_miles: int = 10) -> list[dict]:
        if not self.configured:
            raise RuntimeError("Kroger API credentials are not configured (KROGER_CLIENT_ID / KROGER_CLIENT_SECRET).")
        data = self._get("/locations", {
            "filter.zipCode.near": zip_code, "filter.radiusInMiles": radius_miles, "filter.limit": 20,
        }).get("data", [])
        out = []
        for d in data:
            addr = d.get("address", {})
            out.append({
                "external_id": d["locationId"], "name": d.get("name") or d.get("chain"),
                "chain": d.get("chain"), "address": addr.get("addressLine1", ""), "city": addr.get("city", ""),
                "state": addr.get("state", ""), "zip": addr.get("zipCode", ""),
                "lat": (d.get("geolocation") or {}).get("latitude"), "lng": (d.get("geolocation") or {}).get("longitude"),
            })
        return out

    # -- products -------------------------------------------------------------------
    def _to_offers(self, products: list[dict], loc: Location, score: float = 5.0) -> list[dict]:
        out = []
        for p in products:
            items = p.get("items") or []
            if not items:
                continue
            item = items[0]
            price = (item.get("price") or {})
            regular = price.get("regular")
            if not regular:
                continue
            promo = price.get("promo") or None
            if promo and promo >= regular:
                promo = None
            size_text = item.get("size") or ""
            sv, su, pk = parse_size(size_text)
            aisles = p.get("aisleLocations") or []
            aisle = ""
            section = ""
            if aisles:
                a = aisles[0]
                aisle = " ".join(x for x in (a.get("number") and f"Aisle {a['number']}", a.get("side"),
                                             a.get("shelfNumber") and f"shelf {a['shelfNumber']}") if x)
                section = a.get("description", "")
            image = None
            for img in p.get("images") or []:
                if img.get("perspective") == "front":
                    for s in img.get("sizes", []):
                        if s.get("size") in ("medium", "small", "thumbnail"):
                            image = s.get("url")
                            break
                    if image:
                        break
            brand = p.get("brand") or ""
            name = p.get("description") or ""
            cats = p.get("categories") or []
            fulfillment = item.get("fulfillment") or {}
            in_stock = bool(fulfillment.get("inStore", True))
            out.append(build_offer(
                offer_key=f"kroger:{p['productId']}:{loc.external_id}", provider="kroger",
                product_key=f"kroger:{p.get('upc') or p['productId']}", brand=brand, name=name,
                size_value=sv, size_unit=su, pack_count=pk, category=cats[0] if cats else "",
                upc=p.get("upc", ""), image_url=image, loc=loc, price=float(regular),
                sale_price=float(promo) if promo else None, deal_type="sale" if promo else None,
                deal_text=f"Sale ${promo:.2f}" if promo else None, aisle=aisle, section=section,
                in_stock=in_stock, size_text=size_text, score=score,
            ))
        return out

    def search(self, conn, query: SearchQuery, locations: list[Location]) -> list[dict]:
        locations = [l for l in locations if l.provider == "kroger"]
        if not locations or not self.configured:
            return []
        term = query.text or query.upc
        out = []
        for loc in locations:
            try:
                data = self._get("/products", {
                    "filter.term": term[:100], "filter.locationId": loc.external_id, "filter.limit": 30,
                }).get("data", [])
                out.extend(self._to_offers(data, loc))
            except Exception as e:  # noqa: BLE001
                log.warning("Kroger search failed for %s: %s", loc.name, e)
        return out

    def lookup(self, conn, product_key: str, locations: list[Location]) -> list[dict]:
        locations = [l for l in locations if l.provider == "kroger"]
        if not locations or not self.configured or not product_key.startswith("kroger:"):
            return []
        upc = product_key.split(":", 1)[1]
        out = []
        for loc in locations:
            try:
                data = self._get(f"/products/{upc}", {"filter.locationId": loc.external_id}).get("data")
                if data:
                    out.extend(self._to_offers([data], loc, score=10.0))
            except Exception as e:  # noqa: BLE001
                log.warning("Kroger lookup failed for %s: %s", loc.name, e)
        return out
