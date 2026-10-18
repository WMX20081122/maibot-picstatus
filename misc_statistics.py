"""统计信息模块。

原 nonebot 版依赖 nonebot driver / event_preprocessor / alconna / uninfo 采集机器人信息，
这里全部去掉，改为由插件注入的机器人上下文（set_bot_context）+ 消息计数接口。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx
import psutil

logger = logging.getLogger("WMX20081122_maibot-picstatus")

_process = psutil.Process()
nonebot_run_time: datetime = datetime.fromtimestamp(_process.create_time()).astimezone()

# 机器人运行时上下文（由插件注入）
_bot_context: dict[str, dict[str, Any]] = {}
# self_id -> 首条消息时间（用进程启动时间近似 connection 时长基线）
bot_connect_time: dict[str, datetime] = {}
recv_num: dict[str, int] = {}
send_num: dict[str, int] = {}

# self_id -> {"nick": str, "avatar": bytes|None}
bot_info_cache: dict[str, dict[str, Any]] = {}
bot_avatar_cache: dict[str, bytes | None] = {}


def set_bot_context(self_id: str, nick: str) -> None:
    """由插件在 on_load 注入机器人自身信息（self_id + 昵称）。"""
    self_id = str(self_id)
    bot_connect_time.setdefault(self_id, nonebot_run_time)
    recv_num.setdefault(self_id, 0)
    send_num.setdefault(self_id, 0)
    bot_info_cache.setdefault(self_id, {"nick": nick or "", "avatar": None})
    bot_info_cache[self_id]["nick"] = nick or bot_info_cache[self_id].get("nick", "")
    logger.debug("Bot context set: %s %s", self_id, nick)


def get_all_bot_context() -> dict[str, dict[str, Any]]:
    return dict(bot_info_cache)


def replace_bot_context(self_id: str, nick: str) -> None:
    """用单个真实 self_id 替换全部上下文（避免出现 local + 真实 两张卡片）。"""
    self_id = str(self_id)
    if not self_id or self_id == "local":
        return
    bot_info_cache.clear()
    bot_connect_time.clear()
    recv_num.clear()
    send_num.clear()
    set_bot_context(self_id, nick)


def on_message_received(self_id: str) -> None:
    """每条收到的消息调用一次，累加接收计数。"""
    self_id = str(self_id)
    recv_num[self_id] = recv_num.get(self_id, 0) + 1


def on_message_sent(self_id: str) -> None:
    """发送消息成功后调用，累加发送计数。"""
    self_id = str(self_id)
    send_num[self_id] = send_num.get(self_id, 0) + 1


async def cache_bot_avatar(self_id: str, avatar_bytes: bytes | None):
    bot_avatar_cache[str(self_id)] = avatar_bytes


async def BOT_AVATARS(collected: dict, default_avatar_path, ps_default_avatar) -> dict[str, str]:
    """构造模板所需的 bot_avatars 字典（self_id -> base64 头像，缺失用默认头像）。"""
    import base64
    from pathlib import Path

    bots = collected.get("bots", [])
    result: dict[str, str] = {}
    _default_bytes = None
    for bot_info in bots:
        self_id = getattr(bot_info, "self_id", None) or bot_info.get("self_id")
        avatar_bytes = None
        cached = bot_avatar_cache.get(self_id)
        if cached:
            avatar_bytes = cached
        else:
            avatar_path = (
                ps_default_avatar
                if ps_default_avatar and Path(ps_default_avatar).is_file()
                else default_avatar_path
            )
            if avatar_bytes is None:
                if _default_bytes is None:
                    if Path(avatar_path).is_file():
                        _default_bytes = Path(avatar_path).read_bytes()
                avatar_bytes = _default_bytes
        if avatar_bytes:
            result[self_id] = base64.b64encode(avatar_bytes).decode("utf-8")
        else:
            result[self_id] = ""
    return result


async def fetch_qq_avatar(qq_id: str, timeout: int = 10) -> bytes | None:
    """通过 qlogo 获取 QQ 头像，失败返回 None（不阻塞渲染）。"""
    url = f"https://q1.qlogo.cn/g?b=qq&nk={qq_id}&s=640"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code == 200 and resp.content:
                return resp.content
    except Exception as e:
        logger.debug("Failed to fetch QQ avatar for %s: %s", qq_id, e)
    return None