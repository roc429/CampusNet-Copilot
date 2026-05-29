"""Grafana MCP Server。
获取Grafana仪表盘

工具列表:
- search_dashboard:    按关键字检索 Grafana dashboard 列表。
- get_dashboard_url:   按设备名快速生成可访问的 dashboard 链接。
- render_panel_url:    生成可直接 GET 的 panel 渲染图片 URL(grafana-image-renderer)。  暂未测试
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import httpx
from mcp.server.fastmcp import FastMCP

from mcp_servers._common.http import make_async_client
from mcp_servers._common.logging import configure_logging

logger = configure_logging("GrafanaMCP")


@dataclass(slots=True)
class GrafanaMCPSettings:
    """Grafana MCP 配置。"""

    host: str = os.getenv("GRAFANA_MCP_HOST", "0.0.0.0")
    port: int = int(os.getenv("GRAFANA_MCP_PORT", "9002"))
    transport: str = os.getenv("GRAFANA_MCP_TRANSPORT", "sse")
    request_timeout_seconds: float = float(os.getenv("MCP_REQUEST_TIMEOUT_SECONDS", "8"))
    grafana_base_url: str = os.getenv("GRAFANA_BASE_URL", "http://localhost:3000")
    grafana_api_token: str = os.getenv("GRAFANA_API_TOKEN", "")


settings = GrafanaMCPSettings()

mcp = FastMCP(
    name="GrafanaMCP",
    host=settings.host,
    port=settings.port,
    log_level="INFO",
)


def _grafana_headers() -> dict[str, str]:
    if settings.grafana_api_token:
        return {"Authorization": f"Bearer {settings.grafana_api_token}"}
    return {}


def _abs_grafana_url(rel_or_abs_url: str) -> str:
    if rel_or_abs_url.startswith("http://") or rel_or_abs_url.startswith("https://"):
        return rel_or_abs_url
    return f"{settings.grafana_base_url.rstrip('/')}/{rel_or_abs_url.lstrip('/')}"


@mcp.tool(description="按关键字检索 Grafana dashboard 列表,返回 uid/title/tags/url。")
async def search_dashboard(query: str, limit: int = 10) -> dict[str, Any]:
    """Grafana 仪表盘检索工具。"""

    logger.info("Tool search_dashboard called. query=%s limit=%d", query, limit)
    if not query or not query.strip():
        return {"ok": False, "error": "query 不能为空"}
    limit = max(1, min(int(limit), 50))

    try:
        async with make_async_client(settings.request_timeout_seconds) as client:
            resp = await client.get(
                f"{settings.grafana_base_url}/api/search",
                params={"query": query, "type": "dash-db", "limit": limit},
                headers=_grafana_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        return {"ok": False, "error": "Grafana 查询超时"}
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Tool search_dashboard failed.")
        return {"ok": False, "error": f"Grafana 查询失败: {exc}"}

    if not isinstance(data, list):
        return {"ok": False, "error": "Grafana 返回格式异常"}

    items = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = item.get("url", "")
        items.append(
            {
                "uid": item.get("uid"),
                "title": item.get("title"),
                "tags": item.get("tags", []),
                "url": _abs_grafana_url(url) if isinstance(url, str) and url else None,
            }
        )
    return {"ok": True, "query": query, "count": len(items), "items": items}


@mcp.tool(description="按设备名称快速检索 Grafana 仪表盘并返回直链。")
async def get_dashboard_url(device_name: str) -> dict[str, Any]:
    """根据设备名生成 Grafana 仪表盘链接。"""

    logger.info("Tool get_dashboard_url called. device_name=%s", device_name)
    if not device_name or not device_name.strip():
        return {"ok": False, "error": "device_name 不能为空"}

    try:
        async with make_async_client(settings.request_timeout_seconds) as client:
            resp = await client.get(
                f"{settings.grafana_base_url}/api/search",
                params={"query": "librarynet", "type": "dash-db"},  #按dashboard名检索
                headers=_grafana_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        return {"ok": False, "error": "Grafana 查询超时"}
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Tool get_dashboard_url failed.")
        return {"ok": False, "error": f"Grafana 查询失败: {exc}"}

    if not isinstance(data, list) or not data:
        return {"ok": False, "error": f"未检索到设备 {device_name} 对应看板"}

    first = data[0] if isinstance(data[0], dict) else {}
    url = first.get("url")
    if isinstance(url, str) and url:
        base_url = _abs_grafana_url(url)
    else:
        uid = first.get("uid")
        if not uid:
            return {"ok": False, "error": "Grafana 返回缺少 uid/url 字段"}
        base_url = (
            f"{settings.grafana_base_url.rstrip('/')}/d/{uid}/librarynet"
        )
    
    dashboard_url = (
        f"{base_url}"
        f"?orgId=1"
        f"&from=now%2Fw"
        f"&to=now%2Fw"
        f"&timezone=browser"
        f"&var-device={quote_plus(device_name)}"
    )

    result = {
        "ok": True,
        "device_name": device_name,
        "dashboard_url": dashboard_url,
    }
    logger.info("Tool get_dashboard_url returned ok=True")
    return result


@mcp.tool(description="拼接 Grafana panel 渲染 PNG 链接(需 grafana-image-renderer 已部署)。")
async def render_panel_url(
    dashboard_uid: str,
    panel_id: int,
    var_device: str | None = None,
    width: int = 1000,
    height: int = 500,
    from_seconds_ago: int = 3600,
) -> dict[str, Any]:
    """生成 panel 渲染图片的 GET URL。
    """

    logger.info(
        "Tool render_panel_url called. uid=%s panel=%s var_device=%s",
        dashboard_uid, panel_id, var_device,
    )
    if not dashboard_uid or not dashboard_uid.strip():
        return {"ok": False, "error": "dashboard_uid 不能为空"}

    width = max(200, min(int(width), 4000))
    height = max(150, min(int(height), 3000))
    from_seconds_ago = max(60, int(from_seconds_ago))

    base = settings.grafana_base_url.rstrip("/")
    params = [
        f"orgId=1",
        f"panelId={int(panel_id)}",
        f"width={width}",
        f"height={height}",
        f"from=now-{from_seconds_ago}s",
        f"to=now",
    ]
    if var_device:
        params.append(f"var-device={quote_plus(var_device)}")
    query_string = "&".join(params)

    render_url = f"{base}/render/d-solo/{dashboard_uid}?{query_string}"
    return {
        "ok": True,
        "dashboard_uid": dashboard_uid,
        "panel_id": panel_id,
        "render_url": render_url,
        "auth_required": bool(settings.grafana_api_token),
    }


if __name__ == "__main__":
    logger.info(
        "Starting GrafanaMCP. transport=%s host=%s port=%s grafana=%s token=%s",
        settings.transport,
        settings.host,
        settings.port,
        settings.grafana_base_url,
        "set" if settings.grafana_api_token else "unset",
    )
    mcp.run(transport=settings.transport)  # type: ignore[arg-type]
