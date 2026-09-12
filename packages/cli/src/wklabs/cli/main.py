"""`wklabs` — data operations: sync, status, accounts, import-files, import-raw, rebuild-events."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import typer

from wklabs.lib.accounts import AccountRepo
from wklabs.lib.crypto import TokenCipher
from wklabs.lib.db import Db
from wklabs.lib.logging_setup import setup_logging
from wklabs.lib.settings import Settings, get_settings

app = typer.Typer(
    help="wanikani-labs data tools",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
accounts_app = typer.Typer(
    help="WaniKani accounts (stored in Mongo, tokens encrypted with WKLABS_SECRET_KEY).",
    no_args_is_help=True,
)
app.add_typer(accounts_app, name="accounts")


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


def _repo(db: Db, settings: Settings) -> AccountRepo:
    return AccountRepo(db, TokenCipher.from_settings(settings))


@app.command()
def sync(
    full: bool = typer.Option(False, "--full", help="Ignore updated_after; refetch everything."),
    account: list[str] = typer.Option([], "--account", "-a", help="Limit to account key(s)."),
    no_global: bool = typer.Option(False, "--no-global", help="Skip subjects/srs/voice actors."),
    only_global: bool = typer.Option(False, "--only-global"),
    resource: list[str] = typer.Option([], "--resource", "-r", help="Limit to resource(s)."),
) -> None:
    """Poll WaniKani once and store current state, history and events."""
    from wklabs.lib.sync import SyncEngine

    settings = get_settings()

    async def go(db: Db) -> None:
        engine = SyncEngine(db, _repo(db, settings))
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
        if not res.stats:
            typer.echo("no active accounts — add one via the bot or `wklabs accounts add`")
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
        for acc in await AccountRepo(db).list(status=None):
            a = await account_status(db, acc.key)
            b = stage_buckets(a["stages"])
            typer.echo(
                f"[{acc.key}] {acc.emoji} {acc.label} · {a['username']} · level {a['level']} · "
                f"reviews now {a['reviews_now']} · lessons {a['lessons_now']} · "
                f"reviews 24h {a['reviews_24h']}"
            )
            typer.echo("  " + " · ".join(f"{k} {v}" for k, v in b.items()))

    _run(go)


# ------------------------------------------------------------------ accounts
@accounts_app.command("list")
def accounts_list(all: bool = typer.Option(False, "--all", help="Include removed/purged.")) -> None:
    """Accounts in Mongo: key, label, WaniKani user, status, owner, token hint."""
    from wklabs.lib.accounts import Account

    async def go(db: Db) -> None:
        repo = AccountRepo(db)
        accs = await repo.list(status=None)
        if all:
            accs = [
                Account.from_doc(d) async for d in db.accounts.find({}, sort=[("created_at", 1)])
            ]
        if not accs:
            typer.echo("no accounts — add one via the bot (/accounts) or `wklabs accounts add`")
        for a in accs:
            typer.echo(
                f"{a.emoji} {a.key:<12} {a.label:<18} {a.username} L{a.level} · {a.status}"
                f" · owner {a.owner_tg_id} · token …{a.token_hint} · {a.source}"
            )

    _run(go)


@accounts_app.command("add")
def accounts_add(
    owner: int | None = typer.Option(
        None,
        "--owner",
        help="Telegram user id that owns it (omit: claimed by whoever sends the token).",
    ),
    label: str = typer.Option("", "--label", help="Display name (default: WaniKani username)."),
    private_routes: bool = typer.Option(
        True, "--routes/--no-routes", help="Create default routes to the owner's private chat."
    ),
) -> None:
    """Add (or re-key) an account. The token is read from stdin / a hidden prompt, never argv."""
    from wklabs.lib.accounts import InvalidTokenError, looks_like_token, validate_token
    from wklabs.lib.chats import ChatRepo
    from wklabs.lib.delivery import RouteRepo

    settings = get_settings()
    token = (
        typer.prompt("WaniKani API token", hide_input=True)
        if sys.stdin.isatty()
        else sys.stdin.readline()
    ).strip()
    if not looks_like_token(token):
        typer.echo("that does not look like a WaniKani token (36-char UUID)", err=True)
        raise typer.Exit(2)

    async def go(db: Db) -> None:
        repo = _repo(db, settings)
        try:
            ident = await validate_token(token)
        except InvalidTokenError as exc:
            typer.echo(f"WaniKani rejected the token: {exc}", err=True)
            raise typer.Exit(1) from exc
        existing = await repo.by_wk_id(ident.wk_id)
        if existing is None:
            acc = await repo.create(
                ident, token, owner_tg_id=owner, source="cli", label=label or None
            )
            typer.echo(f"created {acc.key} · {acc.label} ({ident.username}, L{ident.level})")
        else:
            acc = await repo.set_token(existing.key, ident, token)
            if existing.owner_tg_id is None and owner is not None:
                await repo.set_owner(acc.key, owner)
            await RouteRepo(db).resume_account(acc.key)
            typer.echo(f"token replaced for {acc.key} · {acc.label} (was {existing.status})")
        if private_routes and owner is not None:
            await ChatRepo(db).ensure_private(owner)
            await RouteRepo(db).ensure_account_routes(acc.key, owner, created_by=owner)

    _run(go)


def _set_status(key: str, status: str) -> None:
    from wklabs.lib.delivery import RouteRepo

    async def go(db: Db) -> None:
        repo = AccountRepo(db)
        acc = await repo.get(key)
        if acc is None:
            typer.echo(f"no account {key}", err=True)
            raise typer.Exit(1)
        await repo.set_status(key, status)
        if status == "removed":
            await RouteRepo(db).suspend_account(key)
        elif status == "active" and acc.status == "removed":
            await RouteRepo(db).resume_account(key)
        typer.echo(f"{key} · {acc.label}: {acc.status} → {status}")

    _run(go)


@accounts_app.command("pause")
def accounts_pause(key: str) -> None:
    """Stop polling; data and routes stay."""
    _set_status(key, "paused")


@accounts_app.command("resume")
def accounts_resume(key: str) -> None:
    """Resume polling (also revives a removed account)."""
    _set_status(key, "active")


@accounts_app.command("remove")
def accounts_remove(key: str) -> None:
    """Hide from the bot and stop polling; data kept (see `purge`)."""
    _set_status(key, "removed")


@accounts_app.command("purge")
def accounts_purge(key: str, yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Delete ALL per-account data (history included). Only for `removed` accounts."""
    if not yes and not typer.confirm(
        f"Delete every document of account {key} (assignments, history, events…)?"
    ):
        raise typer.Abort()

    async def go(db: Db) -> None:
        try:
            counts = await AccountRepo(db).purge(key)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        typer.echo(" · ".join(f"{k}={v}" for k, v in counts.items()))

    _run(go)


@accounts_app.command("migrate-keys")
def accounts_migrate_keys(
    dry_run: bool = typer.Option(False, "--dry-run", help="Only show what would be renamed."),
) -> None:
    """Rename legacy keys (main/light) to wk_id[:8] in every collection. Stop the bot first."""
    from wklabs.lib.accounts import migrate_keys

    async def go(db: Db) -> None:
        res = await migrate_keys(db, dry_run=dry_run)
        if not res:
            typer.echo("nothing to migrate")
        for r in res:
            rest = " · ".join(f"{k}={v}" for k, v in r.items() if k not in ("old", "new", "wk_id"))
            typer.echo(
                f"{r['old']} → {r['new']} ({r['wk_id']}){' [dry-run]' if dry_run else ''}: {rest}"
            )

    _run(go)


@app.command("gen-key")
def gen_key() -> None:
    """Print a new WKLABS_SECRET_KEY (Fernet). Keep it in 1Password and shared/env."""
    from wklabs.lib.crypto import generate_key

    typer.echo(generate_key())


# ------------------------------------------------------------------- imports
@app.command("import-files")
def import_files(
    root: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    account: list[str] = typer.Option([], "--account", "-a", help="Limit to account(s)."),
    account_map: str = typer.Option(
        "", "--account-map", help="Rename dir keys: `1=07fff792,2=27f9b9f5` for account_1/2."
    ),
) -> None:
    """Import old file snapshots (account_<acc>/<type>/<NNxx>/<id>/...) into history."""
    from wklabs.lib.importer import import_files as _import
    from wklabs.lib.importer_raw import parse_account_map

    async def go(db: Db) -> None:
        counts = await _import(
            db, root, accounts=account or None, account_map=parse_account_map(account_map)
        )
        typer.echo(counts)

    _run(go)


@app.command("import-raw")
def import_raw(
    root: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    account_map: str = typer.Option(
        ..., "--account-map", help="<dir>=<account key>,... for data<N>/ dumps."
    ),
    default_account: str = typer.Option(
        ..., "--default-account", help="Account key for per-account objects under data.v1/."
    ),
) -> None:
    """Import pre-restructure raw dumps (data<N>-MM_DD/<endpoint>/raw, data.v1/) into history."""
    from wklabs.lib.importer_raw import import_raw as _import
    from wklabs.lib.importer_raw import parse_account_map

    async def go(db: Db) -> None:
        counts = await _import(
            db, root, account_map=parse_account_map(account_map), default_account=default_account
        )
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


def main() -> Any:  # pragma: no cover
    return app()


if __name__ == "__main__":  # pragma: no cover
    main()
