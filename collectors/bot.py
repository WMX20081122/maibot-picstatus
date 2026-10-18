from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..config import config
from ..misc_statistics import (
    bot_connect_time,
    get_all_bot_context,
    recv_num,
    send_num,
)
from ..util import format_timedelta
from . import normal_collector


@dataclass
class BotStatus:
    self_id: str
    adapter: str
    nick: str
    bot_connected: str
    msg_rec: str
    msg_sent: str


async def get_bot_status(self_id: str, now_time: datetime) -> BotStatus:
    nick = (
        (info["nick"] or info.get("name") or info.get("id") or "Bot")
        if (info := get_all_bot_context().get(self_id))
        else next(iter(config.nickname), None) or "Bot"
    )
    bot_connected = (
        format_timedelta(now_time - t)
        if (t := bot_connect_time.get(self_id))
        else "未知"
    )

    msg_rec = recv_num.get(self_id)
    msg_sent = send_num.get(self_id)
    msg_rec = "未知" if (msg_rec is None) else str(msg_rec)
    msg_sent = "未知" if (msg_sent is None) else str(msg_sent)

    return BotStatus(
        self_id=self_id,
        adapter="MaiBot",
        nick=nick,
        bot_connected=bot_connected,
        msg_rec=msg_rec,
        msg_sent=msg_sent,
    )


@normal_collector()
async def bots() -> list[BotStatus]:
    now_time = datetime.now().astimezone()
    context = get_all_bot_context()
    if config.ps_show_current_bot_only:
        selected = context and [next(iter(context))]
    else:
        selected = list(context)
    if not selected:
        selected = ["local"]
    return [await get_bot_status(self_id, now_time) for self_id in selected]