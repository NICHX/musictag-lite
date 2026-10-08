"""结构化日志：依赖标准库，输出 key=value 便于收集与检索。"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime


class KeyValueFormatter(logging.Formatter):
    """把日志格式化为 `ts level logger event key=value ...` 的结构化单行文本。"""

    _RESERVED = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        parts = [
            f"ts={timestamp}",
            f"level={record.levelname.lower()}",
            f"logger={record.name}",
            f"event={record.getMessage()}",
        ]
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key.startswith("_"):
                continue
            parts.append(f"{key}={value}")
        if record.exc_info:
            parts.append(f"exc={self.formatException(record.exc_info)!r}")
        return " ".join(parts)


def setup_logging(level: str | int = logging.INFO) -> None:
    """初始化根日志器；重复调用安全。"""
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(KeyValueFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # 降低第三方库噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
