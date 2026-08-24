"""`wklabs-web` — uvicorn on port 8100 (project #10, see DEV.md port registry)."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "wklabs.web.app:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8100")),
        reload=bool(os.environ.get("RELOAD")),
    )


if __name__ == "__main__":
    main()
