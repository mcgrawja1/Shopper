import os
import tempfile

import pytest

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="shopper-test-")

from app import config  # noqa: E402
from pathlib import Path  # noqa: E402

config.DATA_DIR = Path(os.environ["DATA_DIR"])
config.DB_PATH = config.DATA_DIR / "shopper.db"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c
