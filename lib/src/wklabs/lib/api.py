"""WaniKani API v2 client: auth, pagination, ETag, rate limit (60 req/min), retries."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://api.wanikani.com/v2/"
REVISION = "20170710"

Json = dict[str, Any]


class WaniKaniError(Exception):
    def __init__(self, status: int, message: str, url: str = "") -> None:
        super().__init__(f"HTTP {status}: {message} ({url})")
        self.status = status
        self.url = url


@dataclass(slots=True)
class ApiResponse:
    status: int
    data: Json | None  # None on 304 Not Modified
    etag: str | None

    @property
    def not_modified(self) -> bool:
        return self.status == 304


class _RateLimiter:
    """Sliding-window limiter: at most `limit` requests per `window` seconds."""

    def __init__(self, limit: int = 55, window: float = 60.0) -> None:
        self.limit = limit
        self.window = window
        self._hits: deque[float] = deque()

    async def wait(self) -> None:
        while True:
            now = time.monotonic()
            while self._hits and now - self._hits[0] >= self.window:
                self._hits.popleft()
            if len(self._hits) < self.limit:
                self._hits.append(now)
                return
            delay = self.window - (now - self._hits[0]) + 0.05
            log.debug("rate limit: sleeping %.1fs", delay)
            await asyncio.sleep(delay)


class WaniKaniClient:
    def __init__(
        self,
        token: str,
        *,
        http: httpx.AsyncClient | None = None,
        per_minute: int = 55,
        retries: int = 3,
    ) -> None:
        self._own_http = http is None
        self.http = http or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Wanikani-Revision": REVISION,
            "User-Agent": "wanikani-labs/0.1 (+github.com/2vitalik)",
        }
        self.limiter = _RateLimiter(per_minute)
        self.retries = retries
        self.requests_made = 0

    async def aclose(self) -> None:
        if self._own_http:
            await self.http.aclose()

    @staticmethod
    def _url(path: str) -> str:
        return path if path.startswith("http") else BASE_URL + path.lstrip("/")

    async def get(
        self, path: str, params: dict[str, Any] | None = None, *, etag: str | None = None
    ) -> ApiResponse:
        url = self._url(path)
        headers = dict(self.headers)
        if etag:
            headers["If-None-Match"] = etag
        attempt = 0
        while True:
            attempt += 1
            await self.limiter.wait()
            try:
                res = await self.http.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                if attempt > self.retries:
                    raise WaniKaniError(0, f"network error: {exc}", url) from exc
                await asyncio.sleep(2.0 * attempt)
                continue
            self.requests_made += 1
            log.debug("GET %s %s -> %s", url, params or "", res.status_code)
            if res.status_code == 304:
                return ApiResponse(304, None, res.headers.get("etag"))
            if res.status_code == 429:
                reset = res.headers.get("RateLimit-Reset")
                delay = max(1.0, float(reset) - time.time()) if reset else 60.0
                delay = min(delay, 120.0)
                log.warning("429 from WaniKani, sleeping %.0fs", delay)
                await asyncio.sleep(delay)
                if attempt > self.retries + 2:
                    raise WaniKaniError(429, "rate limited", url)
                continue
            if res.status_code >= 500:
                if attempt > self.retries:
                    raise WaniKaniError(res.status_code, res.text[:200], url)
                await asyncio.sleep(3.0 * attempt)
                continue
            if res.status_code >= 400:
                raise WaniKaniError(res.status_code, res.text[:200], url)
            data = res.json()
            if isinstance(data, dict) and "error" in data:
                raise WaniKaniError(int(data.get("code", 0)), str(data["error"]), url)
            return ApiResponse(res.status_code, data, res.headers.get("etag"))

    async def iter_pages(
        self, path: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[Json]:
        """Yield each collection page (`object == "collection"`); follows `pages.next_url`."""
        url: str | None = self._url(path)
        first = True
        while url:
            res = await self.get(url, params if first else None)
            first = False
            page = res.data or {}
            yield page
            url = (page.get("pages") or {}).get("next_url")

    async def iter_items(
        self, path: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[Json]:
        async for page in self.iter_pages(path, params):
            for item in page.get("data") or []:
                yield item
