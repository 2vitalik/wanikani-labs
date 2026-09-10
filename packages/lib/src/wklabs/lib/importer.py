"""Import the 2022-2026 file snapshots (old cron scraper layout) into `history`.

Layout: `<root>/account_<acc>/<type>/<NNxx>/<id>/{info,assign,review}.json`
(latest) and `<root>/.../<id>/<YYYY-MM>/<cat>__<date>__<time>.json` (versions).
Every file is a full WaniKani object with `data_updated_at`, so all of them go
to `history` (unique on version; duplicates skipped). Run `rebuild-events` after.

The file name carries `data_updated_at`, not the fetch time; the file mtime is
the closest thing to it, so it is kept raw as `source_mtime` (unreliable for
files rewritten by later restructures — never used as `fetched_at`).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo.errors import BulkWriteError

from .db import Db
from .resources import RESOURCES
from .sync import history_doc
from .timeutil import utcnow

log = logging.getLogger(__name__)

CATEGORY_TO_RESOURCE = {"info": "subjects", "assign": "assignments", "review": "review_statistics"}
_MONTH = re.compile(r"^\d{4}-\d{2}$")
_SNAP = re.compile(r"^(info|assign|review)__\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2}$")
_PROGRESS_EVERY = 20  # flushes

Json = dict[str, Any]


class HistoryWriter:
    """Batched inserts into `history`; duplicate versions (unique index) are counted, not errors."""

    def __init__(self, db: Db, *, batch: int = 1000) -> None:
        self.db = db
        self.batch = batch
        self.imported_at = utcnow()
        self.counts = {"files": 0, "inserted": 0, "duplicates": 0, "bad": 0}
        self._buf: list[Json] = []
        self._flushes = 0

    def add(
        self, resource_name: str, account: str | None, item: Json, source: Path, root: Path
    ) -> None:
        h = history_doc(
            RESOURCES[resource_name],
            account,
            item,
            fetched_at=None,
            run_kind="import",
            run_id=None,
            prev_data_updated_at=None,
        )
        h["imported_at"] = self.imported_at
        h["source_file"] = str(source.relative_to(root))
        h["source_mtime"] = datetime.fromtimestamp(source.stat().st_mtime, UTC)
        self._buf.append(h)

    async def flush(self, *, force: bool = True) -> None:
        if not self._buf or (not force and len(self._buf) < self.batch):
            return
        try:
            r = await self.db.history.insert_many(self._buf, ordered=False)
            self.counts["inserted"] += len(r.inserted_ids)
        except BulkWriteError as exc:
            errs = exc.details.get("writeErrors", [])
            dups = sum(1 for e in errs if e.get("code") == 11000)
            self.counts["duplicates"] += dups
            self.counts["inserted"] += len(self._buf) - len(errs)
            if len(errs) != dups:
                log.error("import: %d non-duplicate write errors", len(errs) - dups)
        self._buf.clear()
        self._flushes += 1
        if self._flushes % _PROGRESS_EVERY == 0:
            log.info(
                "import: %(files)d files, %(inserted)d inserted, %(duplicates)d dup", self.counts
            )


def iter_files(
    root: Path, account_map: dict[str, str] | None = None
) -> Iterator[tuple[str, str, Path]]:
    """Yield (account, category, path) for every snapshot/latest file, sorted.

    `account_map` renames dir keys (the server writes `account_1`/`account_2`
    after the token keys; our accounts are `main`/`light`).
    """
    for account_dir in sorted(root.iterdir()):
        if not account_dir.is_dir() or not account_dir.name.startswith("account_"):
            continue
        key = account_dir.name.removeprefix("account_")
        account = (account_map or {}).get(key, key)
        for path in sorted(account_dir.rglob("*.json")):
            stem = path.stem
            if stem in CATEGORY_TO_RESOURCE:
                yield account, stem, path
            else:
                m = _SNAP.match(stem)
                if m and _MONTH.match(path.parent.name):
                    yield account, m.group(1), path


async def import_files(
    db: Db,
    root: Path,
    *,
    batch: int = 1000,
    accounts: list[str] | None = None,
    account_map: dict[str, str] | None = None,
) -> dict[str, int]:
    w = HistoryWriter(db, batch=batch)
    for account, category, path in iter_files(root, account_map):
        if accounts and account not in accounts:
            continue
        w.counts["files"] += 1
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            w.counts["bad"] += 1
            log.warning("import: bad file %s: %s", path, exc)
            continue
        if not isinstance(item, dict) or "data_updated_at" not in item or "id" not in item:
            w.counts["bad"] += 1
            log.warning("import: not a WaniKani object: %s", path)
            continue
        w.add(CATEGORY_TO_RESOURCE[category], account, item, path, root)
        await w.flush(force=False)
    await w.flush()
    log.info("import done: %s", w.counts)
    return w.counts
