"""Shopper: grocery price comparison + shopping list builder."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .db import init_db
from .routers import deals, favorites, lists, search, settings, stores

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Shopper", version="0.2.0", lifespan=lifespan)

for r in (search.router, stores.router, favorites.router, lists.router, settings.router, deals.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version}


app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """Serve the single-page frontend for every non-API route."""
    return FileResponse(config.FRONTEND_DIR / "index.html")
