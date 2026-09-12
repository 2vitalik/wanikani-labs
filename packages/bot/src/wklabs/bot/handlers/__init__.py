"""aiogram routers, in inclusion order (first match wins)."""

from .accounts import router as accounts_router
from .admin import router as admin_router
from .chats import router as chats_router
from .delivery import router as delivery_router
from .membership import router as membership_router
from .setup import router as setup_router
from .start import router as start_router

ROUTERS = [
    admin_router,
    membership_router,
    chats_router,
    delivery_router,
    setup_router,
    accounts_router,
    start_router,
]
