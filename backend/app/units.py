"""Size parsing and unit-price normalisation.

Everything is normalised to one of three families so per-unit prices can be
compared and sorted:
  weight -> ounces (oz)
  volume -> fluid ounces (fl oz)
  count  -> pieces (ct)
"""
from __future__ import annotations

import re
from typing import Optional

# unit -> (family, multiplier to base unit)
UNITS: dict[str, tuple[str, float]] = {
    "oz": ("weight", 1.0), "ounce": ("weight", 1.0), "ounces": ("weight", 1.0),
    "lb": ("weight", 16.0), "lbs": ("weight", 16.0), "pound": ("weight", 16.0), "pounds": ("weight", 16.0),
    "g": ("weight", 0.035274), "gram": ("weight", 0.035274), "grams": ("weight", 0.035274),
    "kg": ("weight", 35.274),
    "fl oz": ("volume", 1.0), "floz": ("volume", 1.0), "fl. oz": ("volume", 1.0), "fl.oz": ("volume", 1.0),
    "gal": ("volume", 128.0), "gallon": ("volume", 128.0), "gallons": ("volume", 128.0),
    "qt": ("volume", 32.0), "quart": ("volume", 32.0), "quarts": ("volume", 32.0),
    "pt": ("volume", 16.0), "pint": ("volume", 16.0), "pints": ("volume", 16.0),
    "l": ("volume", 33.814), "liter": ("volume", 33.814), "liters": ("volume", 33.814), "ltr": ("volume", 33.814),
    "ml": ("volume", 0.033814),
    "ct": ("count", 1.0), "count": ("count", 1.0), "each": ("count", 1.0), "ea": ("count", 1.0),
    "pc": ("count", 1.0), "pcs": ("count", 1.0), "piece": ("count", 1.0), "pieces": ("count", 1.0),
    "pk": ("count", 1.0), "pack": ("count", 1.0), "roll": ("count", 1.0), "rolls": ("count", 1.0),
    "bag": ("count", 1.0), "bags": ("count", 1.0), "sheet": ("count", 1.0), "sheets": ("count", 1.0),
    "load": ("count", 1.0), "loads": ("count", 1.0), "tablet": ("count", 1.0), "tablets": ("count", 1.0),
    "can": ("count", 1.0), "cans": ("count", 1.0), "bottle": ("count", 1.0), "bottles": ("count", 1.0),
    "dozen": ("count", 12.0), "dz": ("count", 12.0), "bunch": ("count", 1.0), "head": ("count", 1.0),
}

FAMILY_LABEL = {"weight": "oz", "volume": "fl oz", "count": "ct"}
CANONICAL_UNIT = {
    "ounce": "oz", "ounces": "oz", "lbs": "lb", "pound": "lb", "pounds": "lb", "gram": "g", "grams": "g",
    "floz": "fl oz", "fl. oz": "fl oz", "fl.oz": "fl oz", "gallon": "gal", "gallons": "gal",
    "quart": "qt", "quarts": "qt", "pint": "pt", "pints": "pt", "liter": "l", "liters": "l", "ltr": "l",
    "count": "ct", "each": "ct", "ea": "ct", "pc": "ct", "pcs": "ct", "piece": "ct", "pieces": "ct",
    "pk": "ct", "pack": "ct", "rolls": "roll", "bags": "bag", "sheets": "sheet", "loads": "load",
    "tablets": "tablet", "cans": "can", "bottles": "bottle", "dz": "dozen",
}

_UNIT_ALTS = sorted(UNITS.keys(), key=len, reverse=True)
_UNIT_RE = "|".join(re.escape(u) for u in _UNIT_ALTS)
_NUM = r"(\d+(?:\.\d+)?)"
# "12 pack x 12 fl oz", "12 x 12 fl oz", "12pk/12 fl oz", "12 - 12 fl oz cans"
_PACK_RE = re.compile(
    rf"^\s*{_NUM}\s*(?:pack|pk|ct|count|cans?|bottles?|-)?\s*(?:x|×|/|-|of|@)\s*{_NUM}\s*({_UNIT_RE})\b",
    re.I,
)
_SIMPLE_RE = re.compile(rf"{_NUM}\s*({_UNIT_RE})\b", re.I)
_TRAILING_PACK_RE = re.compile(rf"\b{_NUM}\s*(?:pack|pk|ct|count)\b", re.I)


def canonical_unit(u: str) -> str:
    u = u.lower().strip().replace("  ", " ")
    return CANONICAL_UNIT.get(u, u)


def parse_size(text: Optional[str]) -> tuple[Optional[float], Optional[str], int]:
    """Return (size_value, size_unit, pack_count) for a free-form size string.

    >>> parse_size("12 pack x 12 fl oz")
    (12.0, 'fl oz', 12)
    >>> parse_size("5 lb")
    (5.0, 'lb', 1)
    >>> parse_size("18 ct")
    (18.0, 'ct', 1)
    """
    if not text:
        return None, None, 1
    t = text.strip().lower()
    m = _PACK_RE.match(t)
    if m:
        return float(m.group(2)), canonical_unit(m.group(3)), int(float(m.group(1)))
    m = _SIMPLE_RE.search(t)
    if m:
        value, unit = float(m.group(1)), canonical_unit(m.group(2))
        pack = 1
        rest = t[: m.start()] + t[m.end():]
        pm = _TRAILING_PACK_RE.search(rest)
        if pm and unit not in ("ct",):
            pack = int(float(pm.group(1)))
        return value, unit, pack
    return None, None, 1


def family_of(unit: Optional[str]) -> Optional[str]:
    if not unit:
        return None
    entry = UNITS.get(unit.lower())
    return entry[0] if entry else None


def base_quantity(size_value: Optional[float], size_unit: Optional[str], pack_count: int = 1) -> Optional[float]:
    """Total quantity in the family's base unit (oz / fl oz / ct)."""
    if not size_value or not size_unit:
        return None
    entry = UNITS.get(size_unit.lower())
    if not entry:
        return None
    return size_value * entry[1] * max(pack_count or 1, 1)


def unit_price(price: Optional[float], size_value, size_unit, pack_count=1) -> dict:
    """Compute per-unit pricing. Returns dict with unit_price/unit_label plus an
    alternate human-friendly figure (per lb, per gallon, per 100 ct)."""
    out = {"unit_price": None, "unit_label": None, "unit_price_alt": None, "unit_label_alt": None,
           "unit_family": family_of(size_unit)}
    qty = base_quantity(size_value, size_unit, pack_count)
    if price is None or not qty:
        return out
    fam = out["unit_family"]
    up = price / qty
    out["unit_price"] = round(up, 4)
    out["unit_label"] = FAMILY_LABEL[fam]
    if fam == "weight":
        out["unit_price_alt"], out["unit_label_alt"] = round(up * 16, 2), "lb"
    elif fam == "volume":
        if qty >= 64:
            out["unit_price_alt"], out["unit_label_alt"] = round(up * 128, 2), "gal"
        else:
            out["unit_price_alt"], out["unit_label_alt"] = round(up * 12, 2), "12 fl oz"
    elif fam == "count" and qty >= 50:
        out["unit_price_alt"], out["unit_label_alt"] = round(up * 100, 2), "100 ct"
    return out


def effective_price(price: float, sale_price=None, deal_type=None, deal_qty=None, deal_price=None) -> float:
    """Best achievable price for one unit given sale/deal terms.

    bogo      -> buy one get one free: half price per unit when buying two
    multibuy  -> e.g. "2 for $5": deal_price / deal_qty
    sale      -> sale_price
    """
    candidates = [price]
    if sale_price:
        candidates.append(sale_price)
    if deal_type == "bogo":
        candidates.append((sale_price or price) / 2.0)
    elif deal_type == "multibuy" and deal_qty and deal_price:
        candidates.append(deal_price / deal_qty)
    elif deal_type == "coupon" and deal_price:
        candidates.append(max((sale_price or price) - deal_price, 0.0))
    return round(min(candidates), 2)


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
    return _slug_re.sub("-", (s or "").lower()).strip("-")


def product_key_for(brand: str, name: str, size_value, size_unit, pack_count=1) -> str:
    size = ""
    if size_value:
        v = int(size_value) if float(size_value).is_integer() else size_value
        size = f"{v}{size_unit or ''}"
    if pack_count and pack_count > 1:
        size = f"{pack_count}x{size}"
    return "|".join([slugify(brand), slugify(name), slugify(size)])


def format_size(size_value, size_unit, pack_count=1) -> str:
    if not size_value:
        return ""
    v = int(size_value) if float(size_value).is_integer() else size_value
    s = f"{v} {size_unit}" if size_unit else f"{v}"
    if pack_count and pack_count > 1:
        s = f"{pack_count} pack x {s}"
    return s
