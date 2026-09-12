"""Callback data (≤ 64 bytes) and FSM states. Handlers re-check ownership: data is forgeable."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup


class AccCb(CallbackData, prefix="acc"):
    key: str
    action: str  # card delivery rename token pause resume remove remove_yes move subj
    arg: str = ""


class RouteCb(CallbackData, prefix="rt"):
    id: str  # ObjectId hex
    action: str = "toggle"


class SetupCb(CallbackData, prefix="setup"):
    field: str  # acc layout subjects system apply cancel
    value: str = ""


class AdminCb(CallbackData, prefix="adm"):
    action: str  # home users accounts sync sync_full status user approve block unblock
    arg: str = ""


class NavCb(CallbackData, prefix="nav"):
    screen: str  # accounts add cancel help


class AddAccount(StatesGroup):
    token = State()  # data: {"replace": key | ""}


class Rename(StatesGroup):
    label = State()  # data: {"key": key}


class Setup(StatesGroup):
    editing = State()  # data: {"setup": SetupState as dict}
