"""扩展（可安装的刮削源插件）安装/卸载生命周期。"""

from __future__ import annotations

import io
import zipfile


def _provider_keys(client) -> set[str]:
    return {item["key"] for item in client.get("/api/providers").json()}


def test_extension_catalog_and_install_uninstall(client) -> None:
    listing = client.get("/api/extensions").json()
    keys = {item["key"] for item in listing["catalog"]}
    assert "community-cn" in keys

    # 初始未安装：社区源不参与注册
    assert _provider_keys(client).isdisjoint({"netease", "qqmusic", "kugou"})

    installed = client.post("/api/extensions/catalog/community-cn/install")
    assert installed.status_code == 200
    body = installed.json()
    assert body["installed"] is True
    assert set(body["providers"]) == {"netease", "qqmusic", "kugou"}

    # 安装后社区源出现在 Provider 列表（默认关闭）
    providers = {item["key"]: item for item in client.get("/api/providers").json()}
    assert providers["netease"]["enabled"] is False

    # 重复安装 → 400
    assert client.post("/api/extensions/catalog/community-cn/install").status_code == 400

    removed = client.delete("/api/extensions/community-cn")
    assert removed.status_code == 200
    assert set(removed.json()["removed_providers"]) == {"netease", "qqmusic", "kugou"}
    assert _provider_keys(client).isdisjoint({"netease", "qqmusic", "kugou"})


def test_extension_install_from_zip(client) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "demo-ext/extension.json",
            '{"key": "demo-ext", "name": "演示扩展", "providers": ["demo.DemoProvider"]}',
        )
        archive.writestr(
            "demo-ext/demo.py",
            "from app.providers.base import HTTPProvider\n\n\n"
            "class DemoProvider(HTTPProvider):\n"
            "    key = 'demo'\n"
            "    name = '演示'\n"
            "    capabilities = {'metadata'}\n",
        )

    resp = client.post(
        "/api/extensions/install",
        files={"file": ("demo-ext.zip", buf.getvalue(), "application/zip")},
    )
    assert resp.status_code == 200
    assert resp.json()["key"] == "demo-ext"
    assert "demo" in _provider_keys(client)

    assert client.delete("/api/extensions/demo-ext").status_code == 200
    assert "demo" not in _provider_keys(client)


def test_extension_install_rejects_bad_zip(client) -> None:
    resp = client.post(
        "/api/extensions/install",
        files={"file": ("bad.zip", b"not a zip", "application/zip")},
    )
    assert resp.status_code == 400
