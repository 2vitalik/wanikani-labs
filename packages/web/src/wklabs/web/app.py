"""FastAPI backend (phase 3 scaffold): health + status JSON; Vue SPA served from vue/dist."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from wklabs.lib.db import Db
from wklabs.lib.settings import get_settings
from wklabs.lib.status import account_status, sync_status

VUE_DIST = Path(__file__).resolve().parents[4] / "vue" / "dist"
router = APIRouter(prefix="/api")


def _db(request: Request) -> Db:
    return request.app.state.db


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    await _db(request).ping()
    return {"ok": True}


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    db = _db(request)
    s = await sync_status(db)
    accounts = [await account_status(db, a) for a in get_settings().accounts]
    last = s["last_run"]
    return {
        "last_run": {k: v for k, v in last.items() if k != "stats"} if last else None,
        "counts": s["counts"],
        "accounts": accounts,
    }


def create_app(db: Db | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = db or Db.from_settings()
        await app.state.db.ping()
        yield
        if db is None:
            await app.state.db.close()

    app = FastAPI(title="wanikani-labs", lifespan=lifespan)
    app.include_router(router)
    if VUE_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=VUE_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        async def spa(path: str) -> FileResponse:
            return FileResponse(VUE_DIST / "index.html")

    return app


app = create_app()
