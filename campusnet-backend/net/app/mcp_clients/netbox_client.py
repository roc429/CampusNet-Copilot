"""NetBox MCP client facade.

The public functions stay small and agent-friendly while this module handles
MCP envelopes and a mock fallback for local development when NetBox MCP is not
running.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.mcp.client import get_standard_mcp_manager

logger = logging.getLogger(__name__)


_MOCK_DEVICES: dict[str, dict[str, Any]] = {
    "AP-LIB-3F-01": {"device_id": "AP-LIB-3F-01", "name": "AP-LIB-3F-01", "role": "ap", "location": "图书馆三楼"},
    "AP-LIB-3F-02": {"device_id": "AP-LIB-3F-02", "name": "AP-LIB-3F-02", "role": "ap", "location": "图书馆三楼"},
    "SW-LIB-AGG-01": {"device_id": "SW-LIB-AGG-01", "name": "SW-LIB-AGG-01", "role": "switch", "location": "图书馆三楼"},
    "AP-DORM-01": {"device_id": "AP-DORM-01", "name": "AP-DORM-01", "role": "ap", "location": "宿舍区"},
    "SW-AGG-DORM-01": {"device_id": "SW-AGG-DORM-01", "name": "SW-AGG-DORM-01", "role": "aggregation_switch", "location": "宿舍区"},
}

_MOCK_NEIGHBORS: dict[str, dict[str, list[str]]] = {
    "AP-LIB-3F-01": {"upstream": ["SW-LIB-AGG-01"], "downstream": []},
    "AP-LIB-3F-02": {"upstream": ["SW-LIB-AGG-01"], "downstream": []},
    "SW-LIB-AGG-01": {"upstream": [], "downstream": ["AP-LIB-3F-01", "AP-LIB-3F-02"]},
    "AP-DORM-01": {"upstream": ["SW-AGG-DORM-01"], "downstream": []},
    "SW-AGG-DORM-01": {"upstream": [], "downstream": ["AP-DORM-01"]},
}


async def search_devices(query: str) -> list[dict[str, Any]]:
    try:
        devices = await _get_netbox_objects("dcim.device", {"name__ic": query}, limit=20)
        return [_normalize_device(item) for item in devices]
    except Exception as exc:  # noqa: BLE001
        logger.warning("NetBox MCP search_devices failed, using mock fallback. query=%s error=%s", query, exc)
        return _mock_search_devices(query)


async def get_devices_by_location(location: str) -> list[dict[str, Any]]:
    normalized_location = _normalize_location_query(location)
    try:
        devices = await _get_netbox_objects("dcim.device", {}, limit=100)
        matched = [
            _normalize_device(item)
            for item in devices
            if _device_matches_location(item, normalized_location)
        ]
        if matched:
            return matched
        # Some NetBox instances expose only name/site filters through MCP.
        return await search_devices(_location_to_device_keyword(normalized_location))
    except Exception as exc:  # noqa: BLE001
        logger.warning("NetBox MCP get_devices_by_location failed, using mock fallback. location=%s error=%s", location, exc)
        return _mock_devices_by_location(normalized_location)


async def get_device_detail(device_id: str) -> dict[str, Any]:
    try:
        devices = await _get_netbox_objects("dcim.device", {"name": device_id}, limit=1)
        if not devices:
            devices = await _get_netbox_objects("dcim.device", {"name__ic": device_id}, limit=1)
        if devices:
            return _normalize_device(devices[0])
    except Exception as exc:  # noqa: BLE001
        logger.warning("NetBox MCP get_device_detail failed, using mock fallback. device_id=%s error=%s", device_id, exc)
    fallback = _MOCK_DEVICES.get(device_id.upper(), {"device_id": device_id, "name": device_id, "status": "unknown"})
    return {**fallback, "source": "mock_fallback"}


async def get_device_neighbors(device_id: str) -> dict[str, Any]:
    try:
        detail = await get_device_detail(device_id)
        raw_id = detail.get("id")
        if raw_id is None:
            return {"upstream": [], "downstream": [], "interfaces": []}
        interfaces = await _get_netbox_objects("dcim.interface", {"device_id": raw_id}, limit=50)
        return {
            "upstream": [],
            "downstream": [],
            "interfaces": [_normalize_interface(item) for item in interfaces],
            "note": "NetBox MCP returned interface inventory; cable neighbor expansion can be added when cable objects are exposed.",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("NetBox MCP get_device_neighbors failed, using mock fallback. device_id=%s error=%s", device_id, exc)
        return _MOCK_NEIGHBORS.get(device_id.upper(), {"upstream": [], "downstream": []})


async def get_device_links(device_id: str) -> list[dict[str, Any]]:
    neighbors = await get_device_neighbors(device_id)
    links = [{"from": device_id, "to": peer, "direction": "upstream"} for peer in neighbors.get("upstream", [])]
    links.extend({"from": device_id, "to": peer, "direction": "downstream"} for peer in neighbors.get("downstream", []))
    for interface in neighbors.get("interfaces", []):
        links.append({"device_id": device_id, "interface": interface, "direction": "interface"})
    return links


async def get_affected_scope(device_id: str) -> dict[str, Any]:
    neighbors = await get_device_neighbors(device_id)
    return {
        "device_id": device_id,
        "affected_downstream": neighbors.get("downstream", []),
        "upstream_dependency": neighbors.get("upstream", []),
        "interfaces": neighbors.get("interfaces", []),
    }


async def _get_netbox_objects(object_type: str, filters: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    manager = get_standard_mcp_manager()
    try:
        result = await manager.call_remote_tool(
            server_name="netbox",
            tool_name="netbox_get_objects",
            arguments={"object_type": object_type, "filters": filters, "limit": limit},
        )
    except BaseException as exc:  # noqa: BLE001
        await manager.close()
        raise RuntimeError(f"NetBox MCP call failed: {type(exc).__name__}: {exc}") from exc
    payload = _extract_payload(result)
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError(str(payload.get("error") or payload))
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return [item for item in payload["results"] if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(object_type), list):
        return [item for item in payload[object_type] if isinstance(item, dict)]
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _extract_payload(envelope: dict[str, Any]) -> Any:
    structured = envelope.get("structured_content")
    if structured:
        return structured
    text = envelope.get("text")
    if isinstance(text, str) and text.strip():
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
    return envelope


def _normalize_device(item: dict[str, Any]) -> dict[str, Any]:
    role = item.get("role")
    location = item.get("location")
    site = item.get("site")
    return {
        **item,
        "device_id": item.get("name") or item.get("device_id") or str(item.get("id", "")),
        "name": item.get("name") or item.get("display") or item.get("device_id"),
        "role": _name_from_nested(role),
        "location": _name_from_nested(location) or _name_from_nested(site) or "",
        "site": _name_from_nested(site),
        "source": "netbox_mcp",
    }


def _normalize_interface(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "type": _name_from_nested(item.get("type")) or item.get("type"),
        "enabled": item.get("enabled"),
        "description": item.get("description"),
    }


def _name_from_nested(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("display") or value.get("slug") or "")
    if value is None:
        return ""
    return str(value)


def _device_matches_location(item: dict[str, Any], location: str) -> bool:
    haystack = json.dumps(item, ensure_ascii=False)
    candidates = {location, location.replace("三楼", "三层"), location.replace("三层", "三楼")}
    if "图书馆" in location:
        candidates.update({"图书馆", "library", "LIB"})
    if "宿舍" in location:
        candidates.update({"宿舍", "dorm", "DORM"})
    return any(candidate and candidate in haystack for candidate in candidates)


def _normalize_location_query(location: str) -> str:
    return location.replace("3F", "三楼").replace("三层", "三楼")


def _location_to_device_keyword(location: str) -> str:
    if "图书馆" in location:
        return "LIB"
    if "宿舍" in location:
        return "DORM"
    return location


def _mock_search_devices(query: str) -> list[dict[str, Any]]:
    normalized = query.upper()
    return [
        {**device, "source": "mock_fallback"}
        for device_id, device in _MOCK_DEVICES.items()
        if normalized in device_id or query in str(device.get("location", ""))
    ]


def _mock_devices_by_location(location: str) -> list[dict[str, Any]]:
    if "图书馆" in location:
        keys = ["AP-LIB-3F-01", "AP-LIB-3F-02", "SW-LIB-AGG-01"]
    elif "宿舍" in location:
        keys = ["AP-DORM-01", "SW-AGG-DORM-01"]
    else:
        keys = []
    return [{**_MOCK_DEVICES[key], "source": "mock_fallback"} for key in keys]
