"""Import the 2022-2026 file snapshots (old cron scraper layout) into `history`.

Layout: `<root>/account_<acc>/<type>/<NNxx>/<id>/{info,assign,review}.json`
(latest) and `<root>/.../<id>/<YYYY-MM>/<cat>__<date>__<time>.json` (versions).
Every file is a full WaniKani object with `data_updated_at`, so all of them go
to `history` (unique on version; duplicates skipped). Run `rebuild-events` after.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
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


def iter_files(root: Path) -> Iterator[tuple[str, str, Path]]:
    """Yield (account, category, path) for every snapshot/latest file."""
    for account_dir in sorted(root.iterdir()):
        if not account_dir.is_dir() or not account_dir.name.startswith("account_"):
            continue
        account = account_dir.name.removeprefix("account_")
        for path in account_dir.rglob("*.json"):
            stem = path.stem
            if stem in CATEGORY_TO_RESOURCE:
                yield account, stem, path
            else:
                m = _SNAP.match(stem)
                if m and _MONTH.match(path.parent.name):
                    yield account, m.group(1), path


async def import_files(
    db: Db, root: Path, *, batch: int = 1000, accounts: list[str] | None = None
) -> dict[str, int]:
    counts = {"files": 0, "inserted": 0, "duplicates": 0, "bad": 0}
    imported_at = utcnow()
    buf: list[dict[str, Any]] = []

    async def flush() -> None:
        if not buf:
            return
        try:
            r = await db.history.insert_many(buf, ordered=False)
            counts["inserted"] += len(r.inserted_ids)
        except BulkWriteError as exc:
            errs = exc.details.get("writeErrors", [])
            dups = sum(1 for e in errs if e.get("code") == 11000)
            counts["duplicates"] += dups
            counts["inserted"] += len(buf) - len(errs)
            if len(errs) != dups:
                log.error("import: %d non-duplicate write errors", len(errs) - dups)
        buf.clear()

    for account, category, path in iter_files(root):
        if accounts and account not in accounts:
            continue
        counts["files"] += 1
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            counts["bad"] += 1
            log.warning("import: bad file %s: %s", path, exc)
            continue
        if not isinstance(item, dict) or "data_updated_at" not in item or "id" not in item:
            counts["bad"] += 1
            continue
        res = RESOURCES[CATEGORY_TO_RESOURCE[category]]
        h = history_doc(
            res,
            account,
            item,
            fetched_at=None,
            run_kind="import",
            run_id=None,
            prev_data_updated_at=None,
        )
        h["imported_at"] = imported_at
        h["source_file"] = str(path.relative_to(root))
        buf.append(h)
        if len(buf) >= batch:
            await flush()
            if counts["files"] % 20000 == 0:
                log.info(
                    "import: %(files)d files, %(inserted)d inserted, %(duplicates)d dup", counts
                )
    await flush()
    log.info("import done: %s", counts)
    return counts
