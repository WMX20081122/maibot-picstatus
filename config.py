"""PicStatus-Re — MaiBot 移植版配置。

包含两部分：
1. ``ConfigModel``：与 CLI 采集/渲染逻辑直接交互的框架无关配置模型（模块级 ``config``）。
2. ``PicStatusConfig``：MaiBot 插件声明用强类型配置模型（PluginConfigBase），
   WebUI 与 config.toml 使用，由 plugin.py 同步到 ``ConfigModel``。
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal

from pydantic import AnyHttpUrl, BaseModel, Field

from maibot_sdk import Field as SDKField
from maibot_sdk import PluginConfigBase

# ── 路径（基于插件目录，不使用 nonebot_plugin_localstore）──
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"
BG_PRELOAD_CACHE_DIR = CACHE_DIR / "bg_preload"
RES_PATH = BASE_DIR / "res"
ASSETS_PATH = RES_PATH / "assets"
TEMPLATE_PATH = RES_PATH / "templates"
DEFAULT_BG_PATH = ASSETS_PATH / "default_bg_0.webp"
DEFAULT_AVATAR_PATH = ASSETS_PATH / "default_avatar.webp"

ProcSortByType = Literal["cpu", "mem"]


class TestSiteCfg(BaseModel):
    name: str
    url: AnyHttpUrl
    use_proxy: bool = False


class ConfigModel(BaseModel):
    # region behavior
    proxy: str | None = None
    ps_template: str = "default"
    ps_command: list[str] = ["状态", "status"]
    ps_only_su: bool = False
    ps_need_at: bool = False
    ps_reply_target: bool = True
    ps_req_timeout: int | None = 10
    # endregion

    # region style
    ps_bg_provider: str = "local"
    ps_bg_preload_count: int = 2
    ps_bg_local_path: Path = ASSETS_PATH
    ps_default_avatar: Path = DEFAULT_AVATAR_PATH
    # endregion

    # region collectors/base
    ps_collect_interval: int = 5
    ps_default_collect_cache_size: int = 1
    ps_collect_cache_size: dict[str, int] = Field(default_factory=dict)
    # endregion

    # region header
    ps_use_env_nick: bool = False
    ps_show_current_bot_only: bool = False
    ps_disconnect_reset_counter: bool = True
    ps_bot_qq: str = ""
    # endregion

    # region disk
    ps_ignore_parts: list[str] = []
    ps_ignore_bad_parts: bool = False
    ps_sort_parts: bool = True
    ps_sort_parts_reverse: bool = False
    ps_ignore_disk_ios: list[str] = [r"^(loop|zram)\d*$"]
    ps_ignore_no_io_disk: bool = False
    ps_sort_disk_ios: bool = True
    # endregion

    # region network
    ps_ignore_nets: list[str] = [r"^lo(op)?\d*$|^(Loopback|本地连接)"]
    ps_ignore_0b_net: bool = False
    ps_sort_nets: bool = True
    ps_test_sites: list[TestSiteCfg] = [
        TestSiteCfg(name="百度", url="https://www.baidu.com/"),
        TestSiteCfg(name="Google", url="https://www.google.com/", use_proxy=True),
    ]
    ps_sort_sites: bool = True
    ps_test_timeout: int = 3
    # endregion

    # region process
    ps_proc_len: int = 5
    ps_ignore_procs: list[str] = ["^System Idle Process$"]
    ps_proc_sort_by: ProcSortByType = "cpu"
    ps_proc_cpu_max_100p: bool = False
    # endregion

    # region builtin
    superusers: set[str] = Field(default_factory=set)
    nickname: set[str] = Field(default_factory=set)
    # endregion


config = ConfigModel()


def apply_config(values: dict) -> None:
    """原地用一组值重建模块级 ``config``，保证 ``from ..config import config`` 的引用始终生效。"""
    obj = ConfigModel.model_validate(values)
    config.__dict__.update(obj.__dict__)


# ─────────────────────────── MaiBot 强类型配置 ───────────────────────────


class PluginSection(PluginConfigBase):
    __ui_label__: ClassVar = "插件"
    __ui_order__: ClassVar = 0

    enabled: bool = SDKField(
        default=True,
        description="是否启用本插件。",
        json_schema_extra={"hint": "总开关，关闭后不再响应「状态」指令。", "label": "启用插件", "order": 0},
    )
    config_version: str = SDKField(
        default="1.0.0",
        json_schema_extra={"disabled": True, "hidden": True, "label": "配置版本", "order": 99},
    )


class AdminSection(PluginConfigBase):
    __ui_label__: ClassVar = "管理员"
    __ui_order__: ClassVar = 1

    superusers: list[str] = SDKField(
        default_factory=list,
        description="管理员 QQ 号列表（ps_only_su 开启时仅这些人可用）。",
        json_schema_extra={"label": "管理员 QQ", "order": 0, "placeholder": "请输入 QQ 号"},
    )
    nickname: list[str] = SDKField(
        default_factory=list,
        description="机器人昵称（用于卡片显示；无法从网络获取时回退此昵称）。",
        json_schema_extra={"label": "机器人昵称", "order": 1},
    )


class BehaviorSection(PluginConfigBase):
    __ui_label__: ClassVar = "行为"
    __ui_order__: ClassVar = 2

    ps_command: list[str] = SDKField(
        default_factory=lambda: ["状态", "status"],
        description="触发指令（纯文本完全匹配其中任意一项即触发）。",
        json_schema_extra={"label": "触发指令", "order": 0},
    )
    ps_only_su: bool = SDKField(
        default=False,
        description="是否仅允许管理员使用。",
        json_schema_extra={"label": "仅管理员", "order": 1},
    )
    ps_need_at: bool = SDKField(
        default=False,
        description="是否需要 @机器人 才触发。",
        json_schema_extra={"label": "需要@", "order": 2},
    )
    ps_reply_target: bool = SDKField(
        default=True,
        description="是否回复触发者（多人无意义，按家长群场景默认开启）。",
        json_schema_extra={"label": "回复目标", "order": 3},
    )
    ps_template: str = SDKField(
        default="default",
        description="渲染模板名称。",
        json_schema_extra={"label": "模板", "order": 4},
    )
    ps_req_timeout: int | None = SDKField(
        default=10,
        description="网络测试超时（秒）。",
        json_schema_extra={"label": "网络超时", "order": 5},
    )
    ps_collect_interval: int = SDKField(
        default=5,
        ge=1,
        description="后台定时采集周期（秒）。",
        json_schema_extra={"label": "采集周期(s)", "order": 6},
    )
    ps_bot_qq: str = SDKField(
        default="",
        description="机器人 QQ 号。填写后直接调用 qlogo API 下载头像，无需等待适配器。",
        json_schema_extra={"label": "机器人 QQ 号", "order": 7, "placeholder": "如 10001"},
    )


class StyleSection(PluginConfigBase):
    __ui_label__: ClassVar = "样式"
    __ui_order__: ClassVar = 3

    ps_bg_provider: str = SDKField(
        default="local",
        description="背景来源：local / none。",
        json_schema_extra={"label": "背景来源", "order": 0},
    )
    ps_bg_preload_count: int = SDKField(
        default=2,
        ge=0,
        description="背景预加载数量。",
        json_schema_extra={"label": "背景预载", "order": 1},
    )


class PicStatusConfig(PluginConfigBase):
    plugin: PluginSection = SDKField(default_factory=PluginSection)
    admin: AdminSection = SDKField(default_factory=AdminSection)
    behavior: BehaviorSection = SDKField(default_factory=BehaviorSection)
    style: StyleSection = SDKField(default_factory=StyleSection)

    def to_config_model(self) -> dict:
        """把 MaiBot 强类型配置转成内部 ``ConfigModel`` 所需的字段字典。"""
        b = self.behavior
        return {
            "proxy": None,
            "ps_template": b.ps_template,
            "ps_command": list(b.ps_command),
            "ps_only_su": b.ps_only_su,
            "ps_need_at": b.ps_need_at,
            "ps_reply_target": b.ps_reply_target,
            "ps_req_timeout": b.ps_req_timeout,
            "ps_collect_interval": b.ps_collect_interval,
            "ps_bot_qq": str(b.ps_bot_qq or "").strip(),
            "ps_bg_provider": self.style.ps_bg_provider,
            "ps_bg_preload_count": self.style.ps_bg_preload_count,
            "superusers": set(str(x).strip() for x in self.admin.superusers if str(x).strip()),
            "nickname": set(str(x).strip() for x in self.admin.nickname if str(x).strip()),
        }