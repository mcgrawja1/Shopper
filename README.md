# Shopper

Self-hosted grocery price comparison and shopping-list builder. Search for a
specific product ("Kraft Macaroni & Cheese") or a generic one ("bananas"),
compare every size and pack across the stores *you* shop at, sorted by
per-unit price, and build a shopping list that is broken down by store,
location and aisle. Lists can be saved and re-priced later; everything you add
becomes a favorite for one-click reordering.

## Run it (Docker Compose)

```bash
git clone https://github.com/mcgrawja1/Shopper.git
cd Shopper
cp .env.example .env        # optional: set SHOPPER_PORT / Kroger API keys
docker compose up -d --build
```

Open `http://<your-server>:8080`. Data (stores, lists, favorites, settings)
persists in the `shopper-data` Docker volume as a single SQLite file.

## Pages

| Page | What it does |
| --- | --- |
| **Home** | Search form (Brand, Product/Item, Size/pack, Category, Sort, store chips) with type-ahead on every text field. Results are grouped by product so you can pick which size / pack to buy (e.g. Sprite 12 / 24 / 30 pack), each expanded into a per-store table with price, per-unit price, aisle, deal and stock. The right sidebar is the current list broken down by store → aisle with totals, deal savings, quantity controls, Save / Load / Re-price / Print / Clear. |
| **Stores** | Choose chains (Walmart, Sam's Club, Aldi, Commissary, Trader Joe's, Winn-Dixie, Publix, Target, Costco, Kroger) and tick the exact locations to include in searches. Add your own locations. Chains backed by a live provider get **Find nearby** by ZIP. |
| **Favorites** | Every product ever added to a list. "Add cheapest" re-prices it at your stores and adds the best offer; "Choose store…" shows every store's price. |
| **Shopping Lists** | Saved lists: view breakdown, Load, Load & re-price (moves each item to today's cheapest store, or keeps the store and refreshes the price, per Settings), Rename, Delete. |
| **Settings** | Home ZIP and radius, default sort, in-stock filter, re-price strategy, live-provider status, and (Phase 2) rewards / membership / subscription accounts. |

## Deals (Phase 2)

Offers can carry a deal (`bogo`, `multibuy` such as "3 for $19", `sale`, or
`coupon`). The *effective* per-unit price used for sorting accounts for the
deal, deal badges appear in results, and the sidebar shows **Better deals on
your list**: items on your list that are cheaper with a deal at another
selected store, with a one-click switch. `/api/deals` lists all current deals
at your stores.

## Where prices come from

Retailers do not publish free price APIs, so Shopper uses a pluggable
provider layer (`backend/app/providers/`):

* **Local catalog** (built-in): ~175 common grocery and household products with
  sizes, pack variants, aisles and deals across all ten chains. Prices are
  chain-level samples so every page works out of the box. Swap or extend this
  data in `backend/seed/products.json` and bump `SEED_VERSION` in
  `backend/app/config.py`.
* **Kroger family (live)**: real products, prices, promos, aisle locations and
  store lookup through the public Kroger Products API. Create a free app at
  <https://developer.kroger.com>, put the keys in `.env`, restart. Until keys
  are present, Kroger locations fall back to catalog prices with a notice.
* Adding another live source (Walmart affiliate API, a scraper you run
  yourself, a CSV you maintain) means implementing `Provider.search()` and
  `Provider.lookup()` in a new module and registering it in
  `providers/registry.py`; every page picks it up automatically.

Per-unit pricing normalises weight to ounces, volume to fluid ounces and
counts to pieces, with a friendlier secondary figure (per lb, per gallon, per
100 ct) shown alongside.

## Development

```bash
pip install -r backend/requirements.txt pytest
cd backend
uvicorn app.main:app --reload --port 8000   # DATA_DIR defaults to ../data
python -m pytest tests
```

The frontend is dependency-free ES modules in `frontend/` served by FastAPI;
no build step. API docs are at `/docs`.

## Layout

```
docker-compose.yml, Dockerfile, .env.example
backend/
  app/main.py          FastAPI app + static hosting
  app/db.py            SQLite schema + seed loader
  app/units.py         size parsing, unit-price + deal math
  app/providers/       catalog (local), kroger (live), registry (orchestration)
  app/routers/         search, stores, favorites, lists, settings, deals
  seed/                chains.json (chains, locations, aisle maps), products.json
  tests/
frontend/
  index.html, css/app.css
  js/app.js            router, shared state, list sidebar
  js/pages/            home, stores, favorites, lists, settings
```
