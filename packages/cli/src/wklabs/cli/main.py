"""`wklabs` — data operations: sync, status, import-files, rebuild-events."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import typer

from wklabs.lib.db import Db
from wklabs.lib.logging_setup import setup_logging
from wklabs.lib.settings import get_settings

app = typer.Typer(
    help="wanikani-labs data tools",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _run[T](fn: Callable[[Db], Awaitable[T]]) -> T:
    settings = get_settings()
    setup_logging(settings.log_level)

    async def main() -> T:
        db = Db.from_settings(settings)
        try:
            await db.ping()
            await db.ensure_indexes()
            return await fn(db)
        finally:
            await db.close()

    return asyncio.run(main())


@app.command()
def sync(
    full: bool = typer.Option(False, "--full", help="Ignore updated_after; refetch everything."),
    account: list[str] = typer.Option([], "--account", "-a", help="Limit to account(s)."),
    no_global: bool = typer.Option(False, "--no-global", help="Skip subjects/srs/voice actors."),
    only_global: bool = typer.Option(False, "--only-global"),
    resource: list[str] = typer.Option([], "--resource", "-r", help="Limit to resource(s)."),
) -> None:
    """Poll WaniKani once and store current state, history and events."""
    from wklabs.lib.sync import SyncEngine

    settings = get_settings()

    async def go(db: Db) -> None:
        engine = SyncEngine(db, settings.wk_token)
        try:
            res = await engine.run(
                full=full,
                accounts=account or None,
                include_global=not no_global,
                include_accounts=not only_global,
                resources=resource or None,
            )
        finally:
            await engine.aclose()
        for scope, per in res.stats.items():
            typer.echo(f"[{scope}]")
            for name, st in per.items():
                flag = " (baseline)" if st.baseline else ""
                err = f"  ERROR: {st.error}" if st.error else ""
                typer.echo(
                    f"  {name:<20} fetched={st.fetched:<6} new={st.new:<6} "
                    f"changed={st.changed:<6} unchanged={st.unchanged:<6} "
                    f"events={st.events}{flag}{err}"
                )
        typer.echo(f"events: {len(res.events)} · requests: {res.requests} · ok: {res.ok}")
        raise typer.Exit(0 if res.ok else 1)

    _run(go)


@app.command()
def status() -> None:
    """Last sync run, per-account levels/SRS, pending events."""
    from wklabs.lib.status import account_status, stage_buckets, sync_status

    settings = get_settings()

    async def go(db: Db) -> None:
        s = await sync_status(db)
        last = s["last_run"]
        if last:
            typer.echo(
                f"last run: {last['started_at']:%Y-%m-%d %H:%M:%S} UTC · "
                f"{last['kind']} · ok={last['ok']} · events={last.get('events')} · "
                f"requests={last.get('requests')}"
            )
            if last.get("errors"):
                typer.echo(f"  errors: {last['errors']}")
        else:
            typer.echo("no sync runs yet")
        typer.echo("counts: " + " · ".join(f"{k}={v}" for k, v in s["counts"].items()))
        for acc in settings.accounts:
            a = await account_status(db, acc)
            b = stage_buckets(a["stages"])
            typer.echo(
                f"[{acc}] {a['username']} · level {a['level']} · "
                f"reviews now {a['reviews_now']} · lessons {a['lessons_now']} · "
                f"reviews 24h {a['reviews_24h']}"
            )
            typer.echo("  " + " · ".join(f"{k} {v}" for k, v in b.items()))

    _run(go)


@app.command("import-files")
def import_files(
    root: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    account: list[str] = typer.Option([], "--account", "-a"),
) -> None:
    """Import old file snapshots (account_<acc>/<type>/<NNxx>/<id>/...) into history."""
    from wklabs.lib.importer import import_files as _import

    async def go(db: Db) -> None:
        counts = await _import(db, root, accounts=account or None)
        typer.echo(counts)

    _run(go)


@app.command("rebuild-events")
def rebuild_events(yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Drop `events` and re-derive them from `history` (marks all as notified)."""
    from wklabs.lib.rebuild import rebuild_events as _rebuild

    if not yes and not typer.confirm("This drops the events collection and rebuilds it. Continue?"):
        raise typer.Abort()

    async def go(db: Db) -> None:
        typer.echo(await _rebuild(db))

    _run(go)


@app.command()
def accounts() -> None:
    """List configured accounts (from WK_TOKEN__*)."""
    s = get_settings()
    for acc in s.accounts:
        typer.echo(f"{acc}: token …{s.wk_token[acc][-4:]}")
    if not s.accounts:
        typer.echo("none — set WK_TOKEN__<NAME> in .env")


def main() -> Any:  # pragma: no cover
    return app()


if __name__ == "__main__":  # pragma: no cover
    main()
