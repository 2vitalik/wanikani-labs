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
    action: str = "toggle"  # toggle recreate


class ChatCb(CallbackData, prefix="ch"):
    chat: int
    # card deliver preset test refresh topics stop stop_yes forget close later
    action: str
    arg: str = ""


class AdminCb(CallbackData, prefix="adm"):
    action: str  # home users accounts sync sync_full status user approve block unblock
    arg: str = ""


class NavCb(CallbackData, prefix="nav"):
    screen: str  # accounts add cancel help chats addchat


class AddAccount(StatesGroup):
    token = State()  # data: {"replace": key | ""}


class Rename(StatesGroup):
    label = State()  # data: {"key": key}
