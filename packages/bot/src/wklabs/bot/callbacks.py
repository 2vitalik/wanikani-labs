"""Callback data (≤ 64 bytes) and FSM states. Handlers re-check ownership: data is forgeable."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import State, StatesGroup


class AccCb(CallbackData, prefix="acc"):
    key: str
    # card notif rename token pause resume remove remove_yes · kind addkind add moveall subj
    action: str
    arg: str = ""


class RouteCb(CallbackData, prefix="rt"):
    id: str  # ObjectId hex
    action: str = "toggle"  # card toggle set set2 more reset target test preview recreate
    arg: str = ""


class SessionCb(CallbackData, prefix="ss"):
    """Buttons under a live/final session message."""

    id: str  # session ObjectId hex
    action: str = "end"  # end map


class ViewCb(CallbackData, prefix="sv"):
    """View buttons under a session message: cycle a route setting, re-render in place."""

    s: str  # session ObjectId hex
    r: str  # route ObjectId hex
    opt: str  # items sort group


class ProgressCb(CallbackData, prefix="pg"):
    """`/progress` screen: cycle an option, switch account, refresh, close."""

    key: str  # account key
    opt: str  # levels sort group filter style diff · acc refresh close
    arg: str = ""


class TargetCb(CallbackData, prefix="tgt"):
    """Target picker step (context lives in the PickTarget FSM data)."""

    chat: int  # 0 = back to the chat step
    thread: str = ""  # "" = pick a topic (forum) or General · g General · a auto · n new · <id>


class TopicCb(CallbackData, prefix="tp"):
    chat: int
    thread: int = 0
    action: str = "rename"


class ChatCb(CallbackData, prefix="ch"):
    chat: int
    # card deliver preset test refresh topics stop stop_yes forget close later
    # routes subj sys newtopic rename
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


class PickTarget(StatesGroup):
    """Where a route goes: chat, then (forum) topic. data: key · cat · mode mv|add|all · route."""

    chat = State()
    topic = State()


class TopicName(StatesGroup):
    name = State()  # data: {"chat": id, "thread": id | 0 (new), "resume": PickTarget data | None}
