"""可选 AI 辅助：调用 OpenAI 兼容接口，把文件名解析为结构化标签。

设计约束（对应设计文档 §1.4 默认安全 / §5 隐私）：
- **默认关闭**，仅当 ``AI_ENABLED=true`` 且配置了 ``AI_API_KEY`` 时可用；
- **仅手动触发**（由 API 显式传入 use_ai），不会在扫描/刮削流程中自动调用；
- **只发送文件名字符串**，不上传音频，不发送文件路径；
- 不记录密钥；失败时回退到本地启发式解析。
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.logging import get_logger
from app.services.ai_config import AIConfig, resolve
from app.services.filename_parser import ParsedFilename

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "你是音乐元数据解析助手。用户会给出一个音乐文件名（不含扩展名，可能包含音轨号、"
    "音质标记、括号说明等噪声，且「艺术家」与「标题」的先后顺序不固定）。"
    "请解析出结构化标签，并只返回一个 JSON 对象，不要输出任何解释或代码块标记。"
    "字段为 {"
    '"title": string|null, "artist": string|null, '
    '"album": string|null, "track_no": number|null'
    "}。"
    "无法确定的字段填 null。artist 只保留主要艺术家，不要包含 feat./ft. 之后的合作者。"
    "不要臆造文件名中不存在的信息。"
)

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class AIUnavailableError(RuntimeError):
    """AI 未启用或未配置密钥。"""


def _loads_lenient(content: str) -> dict[str, Any]:
    """解析模型返回；容忍 ```json 代码块包裹。"""
    text = _FENCE.sub("", content.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型未返回 JSON 对象")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("模型返回的不是 JSON 对象")
    return data


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).split("/")[0].strip())
    except (TypeError, ValueError):
        return None


def is_ai_available(session: object | None = None) -> bool:
    """便捷判断（供 /capabilities 使用）。"""
    from app.services.ai_config import is_ai_available as _is_available

    return _is_available(session)


async def parse_filename_with_ai(
    filename: str,
    *,
    config: AIConfig | None = None,
    client: httpx.AsyncClient | None = None,
) -> ParsedFilename:
    """调用 OpenAI 兼容的 /chat/completions 解析文件名。"""
    cfg = config or resolve(None)
    if not cfg.enabled:
        raise AIUnavailableError("AI 辅助未启用（请在设置中开启）")
    if not cfg.api_key:
        raise AIUnavailableError("缺少 API Key")

    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": filename},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}"}

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=cfg.timeout)
    try:
        response = await http.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    finally:
        if owns_client:
            await http.aclose()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"AI 响应结构异常：{exc}") from exc

    parsed = _loads_lenient(content)
    return ParsedFilename(
        title=_clean_str(parsed.get("title")),
        artist=_clean_str(parsed.get("artist")),
        album=_clean_str(parsed.get("album")),
        track_no=_clean_int(parsed.get("track_no")),
        confidence=0.9,
        note="AI 解析",
    )
