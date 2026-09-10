"""Import the pre-restructure dumps (`mochi/.../_old_data`, 2024-03..04) into `history`.

Layouts under `<root>`:
- `data<N>[-MM_DD]/<endpoint>/raw/<name> [pN].json` — raw API pages as fetched
  (`items/` = subjects per type, `summary/` = one report); `data1` = main, `data2` = light;
- `data.v1/<type>/<NNxx>/<id>/<YYYY-MM>/<date>__<time>.json` — single objects (subjects);
  a per-account object here gets `default_account`.
Other top-level dirs (e.g. `new_data/`, an aborted experiment) are skipped and counted.
Resource comes from each object's `object` field. Run `rebuild-events` after.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .db import Db
from .importer import HistoryWriter
from .resources import RESOURCES

log = logging.getLogger(__name__)

Json = dict[str, Any]

RESOURCE_BY_OBJECT = {
    "radical": "subjects",
    "kanji": "subjects",
    "vocabulary": "subjects",
    "kana_vocabulary": "subjects",
    "assignment": "assignments",
    "review_statistic": "review_statistics",
    "level_progression": "level_progressions",
    "report": "summary",
    "reset": "resets",
    "study_material": "study_materials",
    "user": "user",
}
DEFAULT_ACCOUNT_MAP = {"data1": "main", "data2": "light"}
_ACCOUNT_DIR = re.compile(r"^(data\d+)(-\d\d_\d\d)?$")
_SINGLE_DIR = "data.v1"


def parse_account_map(spec: str) -> dict[str, str]:
    """`data1=main,data2=light` -> {"data1": "main", "data2": "light"}."""
    out: dict[str, str] = {}
    for part in spec.split(","):
        if part.strip():
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def iter_objects(
    root: Path, account_map: dict[str, str], default_account: str, counts: dict[str, int]
) -> Iterator[tuple[str, str | None, Json, Path]]:
    """Yield (resource, account, item, path) for every WaniKani object in known layouts."""
    for path in sorted(root.rglob("*.json")):
        top = path.relative_to(root).parts[0]
        m = _ACCOUNT_DIR.match(top)
        if m and m.group(1) in account_map:
            account = account_map[m.group(1)]
        elif top == _SINGLE_DIR:
            account = default_account
        else:
            counts["skipped_files"] += 1
            continue
        counts["files"] += 1
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            counts["bad"] += 1
            log.warning("import-raw: bad file %s: %s", path, exc)
            continue
        if not isinstance(obj, dict):
            counts["bad"] += 1
            continue
        items: list[Any] = obj.get("data") or [] if obj.get("object") == "collection" else [obj]
        for it in items:
            if not isinstance(it, dict) or "data_updated_at" not in it:
                counts["bad"] += 1
                continue
            resource = RESOURCE_BY_OBJECT.get(str(it.get("object")))
            if resource is None or (not RESOURCES[resource].singleton and "id" not in it):
                counts["bad"] += 1
                log.warning("import-raw: unknown object %r in %s", it.get("object"), path)
                continue
            yield resource, account, it, path


async def import_raw(
    db: Db,
    root: Path,
    *,
    account_map: dict[str, str] | None = None,
    default_account: str = "main",
    batch: int = 1000,
) -> dict[str, int]:
    w = HistoryWriter(db, batch=batch)
    w.counts.update({"objects": 0, "skipped_files": 0})
    amap = DEFAULT_ACCOUNT_MAP if account_map is None else account_map
    for resource, account, item, path in iter_objects(root, amap, default_account, w.counts):
        w.counts["objects"] += 1
        w.add(resource, account, item, path, root)
        await w.flush(force=False)
    await w.flush()
    log.info("import-raw done: %s", w.counts)
    return w.counts
