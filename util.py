"""通用工具函数。

原 nonebot 版依赖 cookit，这里将所需的辅助函数内联自实现，去掉 cookit 依赖。
"""

from __future__ import annotations

import logging
import re
import time
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger("WMX20081122_maibot-picstatus")

if TYPE_CHECKING:
    from .collectors.cpu import CpuFreq


def format_timedelta(
    delta,
    day_divider: str = " ",
    day_suffix: str = "天",
) -> str:
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    parts: list[str] = []
    if days > 0:
        parts.append(f"{days}{day_suffix}")
    if hours > 0 or days > 0:
        parts.append(f"{hours:02d}时")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes:02d}分")
    parts.append(f"{seconds:02d}秒")

    return day_divider.join(parts)


format_time_delta_ps = partial(format_timedelta, day_divider=" ", day_suffix="天")


def auto_convert_byte(
    value,
    suffix: str = "B",
    unit_index: int = 0,
    with_space: bool = True,
) -> str:
    units = ["", "K", "M", "G", "T", "P"]
    if value is None:
        return "未知"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return str(value)

    idx = unit_index
    while abs(val) >= 1024 and idx < len(units) - 1:
        val /= 1024
        idx += 1

    space = " " if with_space else ""
    if val == int(val):
        return f"{int(val)}{space}{units[idx]}{suffix}"
    return f"{val:.2f}{space}{units[idx]}{suffix}"


def match_list_regexp(reg_list: list[str], txt: str) -> re.Match | None:
    if not reg_list:
        return None
    for r in reg_list:
        try:
            match = re.search(r, txt)
            if match:
                return match
        except re.error:
            continue
    return None


def format_cpu_freq(freq: "CpuFreq") -> str:
    if not getattr(freq, "current", None):
        return "主频未知"
    current_str = auto_convert_byte(freq.current, suffix="Hz", unit_index=2, with_space=False)
    if not getattr(freq, "max", None):
        return current_str
    if freq.max == freq.current:
        return auto_convert_byte(freq.max, suffix="Hz", unit_index=2, with_space=False)
    max_str = auto_convert_byte(freq.max, suffix="Hz", unit_index=2, with_space=False)
    return f"{current_str} / {max_str}"


def flatten(iterable):
    for item in iterable:
        if isinstance(item, (list, tuple, set)):
            yield from flatten(item)
        else:
            yield item


class DebugFileWriter:
    def __init__(self, path, prefix: str = "") -> None:
        self.path = Path(path)
        self.prefix = prefix
        self.enabled = False

    def write(self, content, filename: str | None = None) -> None:
        if not self.enabled:
            return
        self.path.mkdir(parents=True, exist_ok=True)
        fname = filename or f"{self.prefix}_{int(time.time())}.txt"
        (self.path / fname).write_text(str(content), encoding="utf-8")


debug = DebugFileWriter(Path.cwd() / "debug", "picstatus")