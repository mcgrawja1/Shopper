"""Runtime configuration, read from environment variables."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
SEED_DIR = BACKEND_DIR / "seed"

DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT_DIR / "data"))
DB_PATH = DATA_DIR / "shopper.db"

KROGER_CLIENT_ID = os.environ.get("KROGER_CLIENT_ID", "").strip()
KROGER_CLIENT_SECRET = os.environ.get("KROGER_CLIENT_SECRET", "").strip()
KROGER_BASE_URL = os.environ.get("KROGER_BASE_URL", "https://api.kroger.com/v1").rstrip("/")

# Bump when seed/*.json changes shape or content so existing DBs reload it.
SEED_VERSION = "2026.09.30-1"
