"""音频指纹计算（F14）：调用 Chromaprint 的 ``fpcalc`` 生成指纹。

``fpcalc`` 是可选外部命令；缺失时抛出 :class:`FingerprintUnavailable`，
由调用方给出明确提示。核心功能不依赖它。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FingerprintUnavailable(RuntimeError):
    """未安装 fpcalc（Chromaprint），无法计算指纹。"""


@dataclass
class Fingerprint:
    """指纹结果：时长（秒）+ 指纹字符串（供 AcoustID 查询）。"""

    duration: int
    value: str


def fpcalc_available() -> bool:
    """检测系统是否安装 fpcalc（用于 /capabilities 与入口开关）。"""
    return shutil.which("fpcalc") is not None


def compute_fingerprint(
    path: str | Path, *, length: int = 120, timeout: float = 30.0
) -> Fingerprint:
    """对音频文件计算指纹。

    只读取音频内容生成指纹，**不修改文件**；指纹用于向 AcoustID 查询，
    不上传音频本体。
    """
    if not fpcalc_available():
        raise FingerprintUnavailable("未安装 fpcalc（Chromaprint），无法计算指纹")

    result = subprocess.run(  # noqa: B603 - 固定命令：fpcalc + 库内文件路径
        ["fpcalc", "-json", "-length", str(length), str(path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"fpcalc 执行失败（{result.returncode}）：{detail}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("fpcalc 返回了非 JSON 输出") from exc

    value = str(data.get("fingerprint") or "")
    if not value:
        raise RuntimeError("fpcalc 未返回指纹")
    return Fingerprint(duration=int(float(data.get("duration") or 0)), value=value)
