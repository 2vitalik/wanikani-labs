import os

import pytest

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ["MONGO_DB"] = "wanikani_labs_test"
os.environ["WKLABS_ENV_FILE"] = "/dev/null"

from wklabs.lib.db import Db


@pytest.fixture
async def db():
    d = Db.connect(os.environ["MONGO_URI"], "wanikani_labs_test")
    await d.ping()
    await d.drop_all()
    await d.ensure_indexes()
    try:
        yield d
    finally:
        await d.drop_all()
        await d.close()
