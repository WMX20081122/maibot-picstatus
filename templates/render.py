from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ..util import auto_convert_byte, format_cpu_freq

if TYPE_CHECKING:
    import jinja2

# PyPNG 渲染引擎（由插件注入，底层使用 ctx.render.html2png）
PngRenderer = Callable[..., Awaitable[bytes]]
_png_renderer: PngRenderer | None = None


def register_png_renderer(renderer: PngRenderer) -> None:
    """由插件注入 HTML→PNG 渲染函数（底层为 MaiBot 的 render.html2png）。"""
    global _png_renderer
    _png_renderer = renderer


async def html_to_png(html: str, **kw: Any) -> bytes:
    """渲染 HTML 为 PNG 字节。

    未注册引擎时抛出 RuntimeError。
    """
    if _png_renderer is None:
        raise RuntimeError("HTML→PNG 渲染引擎尚未注册")
    return await _png_renderer(html, **kw)


def register_global_filter_to(env: "jinja2.Environment"):
    env.filters["auto_convert_byte"] = auto_convert_byte
    env.filters["format_cpu_freq"] = format_cpu_freq
    env.filters["percent_to_color"] = percent_to_color
    env.filters["auto_convert_unit"] = auto_convert_unit


def percent_to_color(percent: float) -> str:
    if percent < 70:
        return "prog-low"
    if percent < 90:
        return "prog-medium"
    return "prog-high"


def auto_convert_unit(value: float, **kw) -> str:
    return auto_convert_byte(value=value, with_space=False, **kw)