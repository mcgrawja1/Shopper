from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db, get_setting, now_iso, set_setting
from ..providers.registry import provider_status

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULTS = {
    "home_zip": "",
    "search_radius": 10,
    "default_sort": "unit_price",
    "in_stock_only": False,
    "show_deals": True,
    "regen_strategy": "cheapest",
}


class SettingsIn(BaseModel):
    home_zip: str | None = None
    search_radius: int | None = Field(None, ge=1, le=100)
    default_sort: str | None = Field(None, pattern="^(unit_price|price|store|relevance)$")
    in_stock_only: bool | None = None
    show_deals: bool | None = None
    regen_strategy: str | None = Field(None, pattern="^(cheapest|same_store)$")


class AccountIn(BaseModel):
    chain_slug: str | None = None
    program: str = Field(min_length=1, max_length=120)
    kind: str = Field("rewards", pattern="^(rewards|subscription|membership|coupon)$")
    member_id: str = ""
    username: str = ""
    notes: str = ""


@router.get("")
def get_settings():
    with get_db() as conn:
        vals = {k: get_setting(conn, k, v) for k, v in DEFAULTS.items()}
        accounts = [dict(r) for r in conn.execute("SELECT * FROM accounts ORDER BY created_at").fetchall()]
    return {"settings": vals, "accounts": accounts, "providers": provider_status()}


@router.put("")
def put_settings(body: SettingsIn):
    with get_db() as conn:
        for k, v in body.model_dump(exclude_none=True).items():
            set_setting(conn, k, v)
        return {k: get_setting(conn, k, v) for k, v in DEFAULTS.items()}


@router.post("/accounts")
def add_account(body: AccountIn):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO accounts(chain_slug, program, kind, member_id, username, notes, created_at) VALUES(?,?,?,?,?,?,?)",
            (body.chain_slug, body.program, body.kind, body.member_id, body.username, body.notes, now_iso()),
        )
        row = conn.execute("SELECT * FROM accounts WHERE id=last_insert_rowid()").fetchone()
        return dict(row)


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Unknown account")
    return {"ok": True}
