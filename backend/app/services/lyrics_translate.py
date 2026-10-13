"""AI 歌词翻译：把整行歌词译成目标语言，输出「原文 + 译文」双语对照标准 LRC。

复用项目既有 AI 配置（OpenAI 兼容接口，默认关闭、仅手动触发）；只发送歌词文本，
不上传音频、不发送文件路径；不记录密钥。失败时抛错由 API 层转成 400。
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.logging import get_logger
from app.services.ai_config import AIConfig, resolve

logger = get_logger(__name__)

# 一行可能带多个时间戳：[mm:ss.xx][mm:ss.xx]歌词
_LRC_LINE = re.compile(r"^(\s*(?:\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\])+)(.*)$")
# [ti:] / [ar:] 等元信息行
_META = re.compile(r"^\[[a-zA-Z]{1,10}:.*\]$")

TARGET_LANGUAGES = {"zh": "简体中文", "en": "English", "ja": "日本語"}
_CHUNK = 80  # 单次请求最多翻译的行数


class LyricsTranslateError(RuntimeError):
    """翻译不可用或失败。"""


def _system_prompt(target: str) -> str:
    language = TARGET_LANGUAGES.get(target, target)
    return (
        "你是歌词翻译助手。用户会给出一个 JSON 对象，其 lines 字段是字符串数组，"
        f"每个元素是一行歌词（可能为空串）。请把每一行翻译成{language}，"
        "保持数组长度与顺序完全一致（空串原样返回空串），忠实翻译、不增删内容、不加解释。"
        '只返回 JSON 对象 {\"lines\": [\"...\", ...]}，不要输出代码块标记。'
    )


def _split_lines(content: str) -> list[tuple[str, str, bool]]:
    """拆成 ``[(时间戳前缀, 文本, 是否可翻译)]``；元信息与空行不可翻译。"""
    parts: list[tuple[str, str, bool]] = []
    for raw in content.splitlines():
        stripped = raw.strip()
        if not stripped:
            parts.append(("", "", False))
            continue
        if _META.match(stripped):
            parts.append((raw, "", False))
            continue
        match = _LRC_LINE.match(raw)
        if match:
            parts.append((match.group(1), match.group(2).strip(), True))
        else:
            parts.append(("", stripped, True))
    return parts


def _rebuild(parts: list[tuple[str, str, bool]], translated: list[str]) -> str:
    """按原行序输出，译文另起一行（沿用相同时间戳）。"""
    lines: list[str] = []
    cursor = 0
    for prefix, text, translatable in parts:
        if not translatable:
            lines.append(prefix)
            continue
        lines.append(f"{prefix}{text}" if prefix else text)
        if cursor < len(translated):
            extra = str(translated[cursor] or "").strip()
            if extra and extra != text:
                lines.append(f"{prefix}{extra}" if prefix else extra)
        cursor += 1
    return "\n".join(lines)


async def _translate_batch(
    texts: list[str], *, target: str, config: AIConfig, client: httpx.AsyncClient | None
) -> list[str]:
    url = f"{config.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {config.api_key}"}
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=config.timeout)
    result: list[str] = []
    try:
        for start in range(0, len(texts), _CHUNK):
            chunk = texts[start : start + _CHUNK]
            payload: dict[str, Any] = {
                "model": config.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": _system_prompt(target)},
                    {"role": "user", "content": json.dumps({"lines": chunk}, ensure_ascii=False)},
                ],
                "response_format": {"type": "json_object"},
            }
            response = await http.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            lines = parsed.get("lines") if isinstance(parsed, dict) else None
            if not isinstance(lines, list):
                raise LyricsTranslateError("AI 未返回 lines 数组")
            result.extend(str(item) for item in lines)
    finally:
        if owns_client:
            await http.aclose()
    return result


async def translate_lyrics(
    content: str,
    *,
    target: str = "zh",
    config: AIConfig | None = None,
    client: httpx.AsyncClient | None = None,
) -> str:
    """把歌词译为目标语言并返回双语对照 LRC。"""
    cfg = config or resolve(None)
    if not cfg.available:
        raise LyricsTranslateError("AI 未启用或未配置密钥（请在设置中开启）")
    if not content.strip():
        raise LyricsTranslateError("歌词内容为空")

    parts = _split_lines(content)
    texts = [text for _prefix, text, translatable in parts if translatable]
    if not any(texts):
        raise LyricsTranslateError("没有可翻译的歌词内容")

    translated = await _translate_batch(texts, target=target, config=cfg, client=client)
    return _rebuild(parts, translated)
