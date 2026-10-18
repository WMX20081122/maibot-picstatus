"""PicStatus-Re — MaiBot 移植版插件入口。

用法：
- 发送「状态」（或 config 中 ps_command 配置的任意一个指令）即可生成设备状态图片。
- 如果 ps_need_at 开启，需要 @机器人 才触发。
- 如果 ps_only_su 开启，仅管理员（admin.superusers）可用。
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from maibot_sdk import Command, HookHandler, MaiBotPlugin

__version__ = "2.3.2"

from . import config as cfg_mod
from . import misc_statistics
from .bg_provider import bg_preloader
from .collectors import (
    collect_all,
    collect_periodic,
    enable_collectors,
    get_periodic_collectors,
    load_builtin_collectors,
    registered_collectors,
)
from .config import PicStatusConfig, apply_config
from .templates import load_builtin_templates, loaded_templates
from .templates.render import register_png_renderer

logger = logging.getLogger("plugin.WMX20081122.maibot-picstatus")


class PicStatusPlugin(MaiBotPlugin):
    config_model = PicStatusConfig

    def __init__(self) -> None:
        super().__init__()
        self._collect_task: asyncio.Task | None = None
        self._png_renderer_registered = False

    async def on_load(self) -> None:
        # 由强类型配置同步到内部 ConfigModel（模块级 config 引用恒定）
        apply_config(self.config.to_config_model())
        cfg = cfg_mod.config

        # 注入机器人自身上下文（self_id + 昵称）
        nick = next(iter(cfg.nickname), None) or "Bot"
        self_id = "local"
        # 首选：配置里直接填了机器人 QQ 号 → 立即用外部 API 下载头像，不依赖适配器时序
        if str(cfg.ps_bot_qq or "").strip():
            self_id = str(cfg.ps_bot_qq).strip()
            misc_statistics.set_bot_context(self_id, nick)
            asyncio.create_task(self._load_avatar(self_id))
        else:
            if self._ctx is not None and hasattr(self._ctx, "api") and hasattr(self._ctx.api, "call"):
                try:
                    info = await self._ctx.api.call("adapter.napcat.system.get_login_info")
                    data = (info or {}).get("data") if isinstance(info, dict) else None
                    self_id = str((data or {}).get("user_id") or "local")
                except Exception as e:
                    logger.warning("获取登录信息失败，使用 local self_id: %s", e)
            misc_statistics.set_bot_context(self_id, nick)
            # 异步拉取真实 QQ 头像（失败静默，BOT_AVATARS 回退默认头像）
            asyncio.create_task(self._load_avatar(self_id))
            # 若加载时适配器未就绪导致 self_id 为 local，后台持续尝试解析真实 self_id
            if self_id == "local":
                asyncio.create_task(self._ensure_real_self_id(nick))

        # 加载模板与采集器
        if cfg.ps_template not in loaded_templates:
            load_builtin_templates()
        current_template = loaded_templates.get(cfg.ps_template)
        if current_template is None:
            raise ValueError(f"Template {cfg.ps_template} not found")

        if (current_template.collectors is None) or any(
            (x not in registered_collectors) for x in current_template.collectors
        ):
            load_builtin_collectors()

        collectors = (
            set(registered_collectors)
            if current_template.collectors is None
            else current_template.collectors
        )
        await enable_collectors(*collectors)

        # 注册 HTML→PNG 渲染引擎（底层用 MaiBot 的 render.html2png）
        self._register_png_renderer()

        # 后台定时采集循环（替代 nonebot_plugin_apscheduler）
        bg_preloader.preload_count = cfg.ps_bg_preload_count
        bg_preloader.start_preload()
        if self._collect_task is None:
            self._collect_task = asyncio.create_task(self._collect_loop(cfg.ps_collect_interval))

        logger.info("PicStatus-Re %s 已加载，指令：%s", __version__, " / ".join(cfg.ps_command))

    async def on_unload(self) -> None:
        if self._collect_task is not None:
            self._collect_task.cancel()
            self._collect_task = None
        # 清理背景预载任务
        for t in list(getattr(bg_preloader, "fire_tasks", set())):
            t.cancel()
        if getattr(bg_preloader, "current_load_task_main", None):
            bg_preloader.current_load_task_main.cancel()
        logger.info("PicStatus-Re 已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        if hasattr(self, "config"):
            apply_config(self.config.to_config_model())
            bg_preloader.preload_count = cfg_mod.config.ps_bg_preload_count
            logger.info("PicStatus-Re 配置已更新(%s)", version)

    # ---- 钩子：统计接收消息 ----

    @HookHandler(
        hook="chat.receive.after_process",
        name="picstatus_recv_counter",
        description="每条接收消息累加接收计数",
    )
    async def _on_received(self, **kwargs: Any) -> None:
        # 尝试从消息里直接取机器人自身 self_id（napcat 在 additional_config.self_id 写入）
        self_id = self._extract_self_id(kwargs or {})
        if self_id and self_id != "local":
            current = self._primary_self_id()
            if current != self_id and current == "local":
                nick = next(iter(cfg_mod.config.nickname), None) or "Bot"
                misc_statistics.replace_bot_context(self_id, nick)
                await self._load_avatar(self_id)
        else:
            self_id = self._primary_self_id()
            # 若仍为 local，适配器应已就绪，补一次真实 self_id 解析（单次尝试，勿阻塞主链）
            if self_id == "local":
                await self._ensure_real_self_id(None, attempts=1)
                self_id = self._primary_self_id()
        if self_id != "local":
            misc_statistics.on_message_received(self_id)

    def _extract_self_id(self, kwargs: dict) -> str:
        """从消息报文里提取机器人自身 self_id（napcat additional_config.self_id）。"""
        try:
            msg = kwargs.get("message") or {}
            mi = msg.get("message_info") or {}
            ac = mi.get("additional_config") or {}
            sid = ac.get("self_id") or mi.get("self_id") or msg.get("self_id")
            if sid:
                return str(sid).strip()
        except Exception:
            pass
        return ""

    @HookHandler(
        hook="send_service.after_send",
        name="picstatus_sent_counter",
        description="每条发送消息累加发送计数",
    )
    async def _on_sent(self, **kwargs: Any) -> None:
        if not kwargs.get("sent"):
            return
        self_id = self._primary_self_id()
        misc_statistics.on_message_sent(self_id)

    def _primary_self_id(self) -> str:
        context = misc_statistics.get_all_bot_context()
        if context:
            return next(iter(context))
        return "local"

    async def _load_avatar(self, self_id: str) -> None:
        if not self_id or self_id == "local":
            return
        try:
            avatar = await misc_statistics.fetch_qq_avatar(self_id)
            logger.info("PicStatus 头像 self_id=%s bytes=%s", self_id, len(avatar) if avatar else 0)
            await misc_statistics.cache_bot_avatar(self_id, avatar)
            if avatar:
                info = misc_statistics.get_all_bot_context().get(self_id)
                if info is not None:
                    info["avatar"] = avatar
        except Exception as e:
            logger.debug("加载头像失败 %s: %s", self_id, e)

    async def _ensure_real_self_id(self, nick: str | None, attempts: int = 10) -> None:
        """适配器就绪后解析真实 self_id 并拉取头像（替换 local 占位）。"""
        if self._ctx is None or not (hasattr(self._ctx, "api") and hasattr(self._ctx.api, "call")):
            return
        for _ in range(max(1, attempts)):
            try:
                info = await self._ctx.api.call("adapter.napcat.system.get_login_info")
                data = (info or {}).get("data") if isinstance(info, dict) else None
                real = str((data or {}).get("user_id") or "").strip()
                if not real or real == "local":
                    raise RuntimeError("user_id 未就绪")
                nick = nick or next(iter(cfg_mod.config.nickname), None) or "Bot"
                misc_statistics.replace_bot_context(real, nick)
                await self._load_avatar(real)
                logger.info("PicStatus 已解析真实 self_id: %s", real)
                return
            except Exception as e:
                logger.debug("等待 self_id 就绪: %s", e)
                await asyncio.sleep(3)

    # ---- 命令 ----

    @Command(
        "状态",
        description="以图片显示当前设备运行状态",
        pattern=r"^\s*(状态|status)\s*$",
    )
    async def cmd_status(self, stream_id: str = "", **kwargs: Any) -> tuple:
        if not stream_id:
            return True, None, 0

        # 发送者 QQ：Command 上下文中从 message_base_info 取（与部署中既有插件一致）
        sender_id = ""
        mbi = kwargs.get("message_base_info") or {}
        if isinstance(mbi, dict):
            ui = mbi.get("user_info") or {}
            if isinstance(ui, dict):
                sender_id = str(ui.get("user_id") or "")
        if not sender_id:
            sender_id = str(kwargs.get("user_id") or "")
        # @机器人校验（best-effort：扫描消息文本是否包含机器人昵称/self_id）
        if cfg_mod.config.ps_need_at:
            nick_list = set(str(x).strip() for x in cfg_mod.config.nickname if str(x).strip())
            for sid in misc_statistics.get_all_bot_context():
                nick_list.add(str(sid))
            text = str(kwargs.get("text") or kwargs.get("content") or "")
            if not (text and any((n and n in text) for n in nick_list)):
                return True, None, 0

        if cfg_mod.config.ps_only_su:
            su = set(str(x).strip() for x in cfg_mod.config.superusers)
            if sender_id not in su:
                await self.ctx.send.text("你没有使用此指令的权限", stream_id)
                return True, None, 0

        try:
            bg, collected = await asyncio.gather(bg_preloader.get(), collect_all())
            ret = await loaded_templates[cfg_mod.config.ps_template].renderer(
                collected=collected,
                bg=bg,
            )
        except Exception:
            logger.exception("获取运行状态图失败")
            await self.ctx.send.text("获取运行状态图片失败，请检查后台输出", stream_id)
            return True, None, 0

        await self.ctx.send.image(
            base64.b64encode(ret).decode("utf-8"),
            stream_id,
        )
        return True, None, 0

    # ---- 工具 ----

    def _register_png_renderer(self) -> None:
        if self._png_renderer_registered:
            return
        self._png_renderer_registered = True

        async def _render_png(html: str, **kw: Any) -> bytes:
            from playwright.async_api import async_playwright

            # 卡片固定宽度（default 模板 .main-background 为 650px），用插件自带
            # playwright 渲染以精确控制视口（消除右侧留白）并使用系统字体（中文不再缺字）
            max_width = int(kw.get("max_width") or 650)
            width = max_width  # body 宽度 = 视口宽度，命中卡片宽度即无右侧空白
            image_format = str(kw.get("image_format") or "png").lower()
            shot_type = "jpeg" if image_format in ("jpeg", "jpg") else "png"

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                try:
                    page = await browser.new_page(
                        viewport={"width": width, "height": 1000},
                        device_scale_factor=2.0,
                    )
                    await page.set_content(html, wait_until="load")
                    # 等待字体/布局就绪
                    await page.wait_for_timeout(250)
                    buf = await page.screenshot(full_page=True, type=shot_type)
                    return buf if isinstance(buf, bytes) else bytes(buf)
                finally:
                    await browser.close()

        register_png_renderer(_render_png)

    async def _collect_loop(self, interval: int) -> None:
        interval = max(interval, 1)
        while True:
            await asyncio.sleep(interval)
            try:
                await collect_periodic(get_periodic_collectors())
            except asyncio.CancelledError:
                break
            except Exception:
                logger.debug("Background collect error", exc_info=True)


def create_plugin() -> PicStatusPlugin:
    return PicStatusPlugin()