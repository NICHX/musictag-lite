"""社区刮削源的公共工具。

合规说明（对应设计文档 §9.2/§9.5）：社区源均为**非官方接口**，可能随时变更或失效，
且涉及第三方平台的内容与版权。因此所有社区源一律 ``default_enabled = False``，
需用户在「设置 → 数据源」中显式启用后才会参与匹配；本项目不下载任何音乐本体。
"""

from __future__ import annotations

from typing import Any

from app.providers.base import ScrapeQuery

# 常见桌面浏览器 UA：这些平台的接口对非浏览器 UA 可能直接拒绝
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def search_keyword(q: ScrapeQuery) -> str:
    """检索关键词：优先「标题 + 艺术家」，缺失时回退文件名提示。"""
    parts = [part for part in (q.title, q.artist) if part]
    if parts:
        return " ".join(parts)
    return (q.filename_hint or "").strip()


def upgrade_https(url: str | None) -> str | None:
    """部分平台的图片地址仍为 http，统一升级为 https，避免混合内容。"""
    if not url:
        return None
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def rank_score(index: int) -> float:
    """平台未提供相关度时的降序分数（仅反映"搜索结果名次"，不代表原唱）；编排层综合打分中占比 15%。"""
    return round(max(0.5, 1.0 - index * 0.05), 3)


def join_names(items: list[dict[str, Any]] | None, key: str = "name") -> str | None:
    """把 [{name: "A"}, {name: "B"}] 拼成 "A, B"。"""
    names = [str(item.get(key)) for item in (items or []) if item.get(key)]
    return ", ".join(names) or None


def to_int_seconds(value: Any, *, milliseconds: bool = False) -> int | None:
    """把时长规整为整秒（``milliseconds=True`` 时按毫秒换算）；非法值返回 None。"""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return int(value) // 1000 if milliseconds else int(value)
