"""aiogram routers, in inclusion order (first match wins)."""

from .accounts import router as accounts_router
from .admin import router as admin_router
from .setup import router as setup_router
from .start import router as start_router

ROUTERS = [admin_router, setup_router, accounts_router, start_router]
