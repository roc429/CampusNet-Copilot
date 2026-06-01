"""DiagnosisAgent 动态工具工厂。"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, create_model

from app.config import settings
from app.mcp.client import RemoteToolInfo, StandardMCPManager, get_standard_mcp_manager

logger = logging.getLogger(__name__)
_INTERFACE_UNSAFE_FIELDS = {"connected_endpoints"}


def _python_type_from_json_schema(schema: dict[str, Any]) -> Any:
    schema_type = _extract_primary_type(schema)
    if isinstance(schema_type, list):
        non_null = [t for t in schema_type if t != "null"]
        schema_type = non_null[0] if non_null else "string"

    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        item_type = _python_type_from_json_schema(schema.get("items", {}))
        return list[item_type]
    if schema_type == "object":
        return dict[str, Any]
    return Any


def _extract_primary_type(schema: dict[str, Any]) -> Any:
    """从 JSON Schema 中提取主类型，兼容 anyOf/oneOf/allOf。"""

    schema_type = schema.get("type")
    if schema_type:
        return schema_type

    for union_key in ("anyOf", "oneOf", "allOf"):
        union_items = schema.get(union_key)
        if not isinstance(union_items, list):
            continue
        for item in union_items:
            if not isinstance(item, dict):
                continue
            item_type = _extract_primary_type(item)
            if item_type:
                return item_type
    return None


def _sanitize_field_name(name: str) -> str:
    sanitized = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    if sanitized and sanitized[0].isdigit():
        sanitized = f"f_{sanitized}"
    return sanitized or "field"


def _coerce_arg_value(value: Any, schema: dict[str, Any]) -> Any:
    if value is None:
        return None

    field_type = _extract_primary_type(schema)
    if isinstance(field_type, list):
        non_null = [t for t in field_type if t != "null"]
        field_type = non_null[0] if non_null else None

    if field_type == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return [value]

    if field_type == "object":
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value.strip())
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return value
        return value

    if field_type == "integer" and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return value

    if field_type == "number" and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value

    if field_type == "boolean" and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False

    # 兜底：即使 schema 不完整，也尽量把 JSON 字符串还原为结构化对象。
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, (list, dict)):
                    return parsed
            except json.JSONDecodeError:
                pass

    return value


def _coerce_arguments(arguments: dict[str, Any], input_schema: dict[str, Any] | None) -> dict[str, Any]:
    schema = input_schema if isinstance(input_schema, dict) else {}
    properties = schema.get("properties", {})
    coerced: dict[str, Any] = {}
    for key, value in arguments.items():
        if value is None:
            continue
        field_schema = properties.get(key, {}) if isinstance(properties, dict) else {}
        if isinstance(field_schema, dict):
            coerced[key] = _coerce_arg_value(value, field_schema)
        else:
            coerced[key] = value
    return coerced


def _build_args_model(tool: RemoteToolInfo) -> type[BaseModel]:
    schema = tool.input_schema or {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    fields: dict[str, tuple[Any, Any]] = {}
    for original_name, prop_schema in properties.items():
        field_name = _sanitize_field_name(original_name)
        py_type = _python_type_from_json_schema(prop_schema if isinstance(prop_schema, dict) else {})
        is_required = original_name in required
        description = prop_schema.get("description") if isinstance(prop_schema, dict) else None

        if field_name == original_name:
            default = ... if is_required else None
            fields[field_name] = (
                py_type,
                Field(default=default, description=description),
            )
        else:
            default = ... if is_required else None
            fields[field_name] = (
                py_type,
                Field(default=default, alias=original_name, description=description),
            )

    if not fields:
        fields["input"] = (
            dict[str, Any],
            Field(
                default_factory=dict,
                description="原始工具输入参数（当远程工具未提供 input schema 时使用）",
            ),
        )

    model_name = f"{tool.server_name}_{tool.name}_Args".replace("-", "_")
    return create_model(
        model_name,
        __base__=BaseModel,
        __config__=ConfigDict(extra="allow", populate_by_name=True),
        **fields,
    )


def _should_retry_netbox_search(result: dict[str, Any]) -> bool:
    """判断 netbox_search_objects 是否需要自动回退到 netbox_get_objects。"""

    if not result.get("ok", False):
        return True

    structured = result.get("structured_content")
    if not isinstance(structured, dict):
        return False
    if not structured:
        return True

    has_any_items = False
    for value in structured.values():
        if isinstance(value, list) and value:
            has_any_items = True
            break
    return not has_any_items


async def _retry_with_netbox_get_objects(
    manager: StandardMCPManager,
    normalized_args: dict[str, Any],
) -> dict[str, Any]:
    """将 search_objects 查询自动降级为 get_objects 精确查询。"""

    query = str(normalized_args.get("query", "")).strip()
    object_types = normalized_args.get("object_types")
    fields = normalized_args.get("fields")
    limit = normalized_args.get("limit", 10)

    if not isinstance(object_types, list) or not object_types:
        object_type = "dcim.device"
    else:
        first = object_types[0]
        object_type = str(first) if first else "dcim.device"

    get_args: dict[str, Any] = {
        "object_type": object_type,
        "limit": int(limit) if isinstance(limit, int | float | str) and str(limit).strip() else 10,
    }
    if query:
        # 先走精确匹配，兼容性最高。
        get_args["filters"] = {"name": query}

    logger.info(
        "Auto retry: netbox_search_objects -> netbox_get_objects args=%s",
        json.dumps(get_args, ensure_ascii=False),
    )
    fallback_result = await manager.call_remote_tool(
        server_name="netbox",
        tool_name="netbox_get_objects",
        arguments=get_args,
    )

    # 若首轮失败，再尝试携带 fields（部分 MCP 实现要求显式 fields）。
    if not fallback_result.get("ok", False) and isinstance(fields, list) and fields:
        get_args_with_fields = {**get_args, "fields": fields}
        logger.info(
            "Auto retry second attempt with fields: %s",
            json.dumps(get_args_with_fields, ensure_ascii=False),
        )
        fallback_result = await manager.call_remote_tool(
            server_name="netbox",
            tool_name="netbox_get_objects",
            arguments=get_args_with_fields,
        )

    # 若仍失败，再降级为模糊匹配（兼容部分部署仅支持 contains 场景）。
    if not fallback_result.get("ok", False) and query:
        get_args_fuzzy = {
            "object_type": object_type,
            "limit": int(limit) if isinstance(limit, int | float | str) and str(limit).strip() else 10,
            "filters": {"name__ic": query},
        }
        logger.info(
            "Auto retry third attempt with fuzzy name filter: %s",
            json.dumps(get_args_fuzzy, ensure_ascii=False),
        )
        fallback_result = await manager.call_remote_tool(
            server_name="netbox",
            tool_name="netbox_get_objects",
            arguments=get_args_fuzzy,
        )

    # MCP get_objects 全部失败时，最后兜底直连 NetBox REST API。
    if not fallback_result.get("ok", False):
        direct_result = await _direct_netbox_lookup(
            query=query,
            limit=int(limit) if isinstance(limit, int | float | str) and str(limit).strip() else 10,
            fields=fields if isinstance(fields, list) else None,
        )
        if direct_result is not None:
            fallback_result = direct_result

    fallback_result["fallback_from"] = "netbox_search_objects"
    return fallback_result


def _project_fields(item: dict[str, Any], fields: list[str] | None) -> dict[str, Any]:
    if not fields:
        return item
    projected: dict[str, Any] = {}
    for key in fields:
        if key in item:
            projected[key] = item[key]
    return projected


def _sanitize_fields_for_object_type(object_type: str, fields: list[str] | None) -> list[str] | None:
    """对已知不稳定字段做收敛，避免 NetBox 4.5.x 某些查询触发 502。"""

    if not fields:
        return fields
    if object_type == "dcim.interface":
        safe = [field for field in fields if field not in _INTERFACE_UNSAFE_FIELDS]
        return safe or None
    return fields


def _object_type_to_endpoint(object_type: str) -> str | None:
    mapping = {
        "dcim.device": "/api/dcim/devices/",
        "dcim.interface": "/api/dcim/interfaces/",
        "dcim.site": "/api/dcim/sites/",
        "dcim.location": "/api/dcim/locations/",
    }
    return mapping.get(object_type)


async def _direct_netbox_lookup(
    query: str,
    limit: int,
    fields: list[str] | None,
) -> dict[str, Any] | None:
    """绕过 netbox-mcp-server，直接调用 NetBox REST API 作为兜底。"""

    base_url = settings.netbox_url.strip().rstrip("/")
    token = settings.netbox_token.strip()
    if not base_url or not token or not query:
        return None

    headers = {"Authorization": f"Token {token}"}
    timeout = httpx.Timeout(float(settings.request_timeout))
    query_terms = _location_query_terms(query) if _looks_like_location_query(query) else [query]

    sites: list[dict[str, Any]] = []
    locations: list[dict[str, Any]] = []
    devices_by_key: dict[str, dict[str, Any]] = {}

    async with httpx.AsyncClient(timeout=timeout, trust_env=not settings.disable_env_proxy) as client:
        for term in query_terms:
            sites.extend(
                await _direct_netbox_list(
                    client=client,
                    base_url=base_url,
                    endpoint="/api/dcim/sites/",
                    params={"name__ic": term, "limit": limit, "offset": 0},
                    headers=headers,
                )
            )
            locations.extend(
                await _direct_netbox_list(
                    client=client,
                    base_url=base_url,
                    endpoint="/api/dcim/locations/",
                    params={"name__ic": term, "limit": limit, "offset": 0},
                    headers=headers,
                )
            )

        for site in sites:
            site_id = site.get("id")
            if site_id is None:
                continue
            for device in await _direct_netbox_list(
                client=client,
                base_url=base_url,
                endpoint="/api/dcim/devices/",
                params={"site_id": site_id, "limit": limit, "offset": 0},
                headers=headers,
            ):
                key = str(device.get("id") or device.get("name"))
                devices_by_key[key] = device

        for location in locations:
            location_id = location.get("id")
            if location_id is None:
                continue
            for device in await _direct_netbox_list(
                client=client,
                base_url=base_url,
                endpoint="/api/dcim/devices/",
                params={"location_id": location_id, "limit": limit, "offset": 0},
                headers=headers,
            ):
                key = str(device.get("id") or device.get("name"))
                devices_by_key[key] = device

        if not devices_by_key and not sites and not locations:
            for term in query_terms:
                for device in await _direct_netbox_list(
                    client=client,
                    base_url=base_url,
                    endpoint="/api/dcim/devices/",
                    params={"name": term, "limit": limit, "offset": 0},
                    headers=headers,
                ):
                    key = str(device.get("id") or device.get("name"))
                    devices_by_key[key] = device
                if not _looks_like_location_query(term):
                    for device in await _direct_netbox_list(
                        client=client,
                        base_url=base_url,
                        endpoint="/api/dcim/devices/",
                        params={"name__ic": term, "limit": limit, "offset": 0},
                        headers=headers,
                    ):
                        key = str(device.get("id") or device.get("name"))
                        devices_by_key[key] = device

    safe_fields = _sanitize_fields_for_object_type("dcim.device", fields)
    projected_devices = [
        _project_fields(device, safe_fields)
        for device in devices_by_key.values()
        if isinstance(device, dict)
    ]
    projected_sites = [_project_fields(site, fields) for site in sites if isinstance(site, dict)]
    projected_locations = [
        _project_fields(location, fields)
        for location in locations
        if isinstance(location, dict)
    ]

    payload = {
        "dcim.device": projected_devices,
        "dcim.site": projected_sites,
        "dcim.location": projected_locations,
    }
    if not any(payload.values()):
        return None

    logger.info(
        "Direct NetBox location-aware lookup succeeded: query=%s devices=%d sites=%d locations=%d",
        query,
        len(projected_devices),
        len(projected_sites),
        len(projected_locations),
    )
    return {
        "ok": True,
        "server_name": "netbox",
        "tool_name": "netbox_location_lookup_direct",
        "structured_content": payload,
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "text": json.dumps(payload, ensure_ascii=False),
    }


async def _direct_netbox_get_objects(
    object_type: str,
    filters: dict[str, Any] | None,
    limit: int,
    fields: list[str] | None,
) -> dict[str, Any] | None:
    """直连 NetBox 查询对象列表（兜底 netbox_get_objects）。"""

    base_url = settings.netbox_url.strip().rstrip("/")
    token = settings.netbox_token.strip()
    endpoint = _object_type_to_endpoint(object_type)
    if not base_url or not token or not endpoint:
        return None

    safe_fields = _sanitize_fields_for_object_type(object_type, fields)
    params: dict[str, Any] = {"limit": limit, "offset": 0}
    if filters:
        params.update(filters)
    if safe_fields:
        params["fields"] = ",".join(safe_fields)

    headers = {"Authorization": f"Token {token}"}
    timeout = httpx.Timeout(float(settings.request_timeout))
    url = f"{base_url}{endpoint}"
    async with httpx.AsyncClient(timeout=timeout, trust_env=not settings.disable_env_proxy) as client:
        response = await client.get(url, params=params, headers=headers)
        if response.status_code != 200:
            logger.warning(
                "Direct get_objects fallback failed: object_type=%s status=%s url=%s",
                object_type,
                response.status_code,
                str(response.request.url),
            )
            return None
        data = response.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        projected = [_project_fields(item, safe_fields) for item in results if isinstance(item, dict)]
        logger.info(
            "Direct get_objects fallback succeeded: object_type=%s count=%d",
            object_type,
            len(projected),
        )
        return {
            "ok": True,
            "server_name": "netbox",
            "tool_name": "netbox_get_objects_direct",
            "structured_content": {object_type: projected},
            "content": [{"type": "text", "text": json.dumps({object_type: projected}, ensure_ascii=False)}],
            "text": json.dumps({object_type: projected}, ensure_ascii=False),
        }


async def _direct_netbox_list(
    client: httpx.AsyncClient,
    base_url: str,
    endpoint: str,
    params: dict[str, Any],
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    response = await client.get(f"{base_url}{endpoint}", params=params, headers=headers)
    if response.status_code != 200:
        logger.warning(
            "Direct NetBox list failed: status=%s url=%s",
            response.status_code,
            str(response.request.url),
        )
        return []
    payload = response.json()
    results = payload.get("results", []) if isinstance(payload, dict) else []
    return [item for item in results if isinstance(item, dict)]


async def _direct_netbox_get_object_by_id(
    object_type: str,
    object_id: int,
    fields: list[str] | None,
) -> dict[str, Any] | None:
    """直连 NetBox 查询单对象（兜底 netbox_get_object_by_id）。"""

    base_url = settings.netbox_url.strip().rstrip("/")
    token = settings.netbox_token.strip()
    endpoint = _object_type_to_endpoint(object_type)
    if not base_url or not token or not endpoint:
        return None

    safe_fields = _sanitize_fields_for_object_type(object_type, fields)
    params: dict[str, Any] = {}
    if safe_fields:
        params["fields"] = ",".join(safe_fields)

    headers = {"Authorization": f"Token {token}"}
    timeout = httpx.Timeout(float(settings.request_timeout))
    url = f"{base_url}{endpoint}{object_id}/"
    async with httpx.AsyncClient(timeout=timeout, trust_env=not settings.disable_env_proxy) as client:
        response = await client.get(url, params=params, headers=headers)
        if response.status_code != 200:
            logger.warning(
                "Direct get_object_by_id fallback failed: object_type=%s object_id=%s status=%s url=%s",
                object_type,
                object_id,
                response.status_code,
                str(response.request.url),
            )
            return None
        data = response.json()
        projected = _project_fields(data, safe_fields) if isinstance(data, dict) else data
        logger.info(
            "Direct get_object_by_id fallback succeeded: object_type=%s object_id=%s",
            object_type,
            object_id,
        )
        return {
            "ok": True,
            "server_name": "netbox",
            "tool_name": "netbox_get_object_by_id_direct",
            "structured_content": projected,
            "content": [{"type": "text", "text": json.dumps(projected, ensure_ascii=False)}],
            "text": json.dumps(projected, ensure_ascii=False),
        }

def _looks_like_location_query(query: str) -> bool:
    return any(
        token in query
        for token in ["图书馆", "宿舍", "教学楼", "三楼", "三层", "区域", "楼", "层"]
    )


def _location_query_terms(query: str) -> list[str]:
    terms = [query, query.replace("三楼", "三层"), query.replace("三层", "三楼")]
    if "图书馆" in query:
        terms.extend(["图书馆", "library"])
    if "宿舍" in query:
        terms.extend(["宿舍", "宿舍区", "dorm"])
    if "教学楼" in query:
        terms.extend(["教学楼"])
    return [term for term in dict.fromkeys(terms) if term]


async def build_hybrid_mcp_tools(
    manager: StandardMCPManager | None = None,
) -> list[StructuredTool]:
    """动态拉取远程 MCP 工具并封装为 LangChain StructuredTool。"""

    mcp_manager = manager or get_standard_mcp_manager()
    remote_tools = await mcp_manager.list_remote_tools()

    if not remote_tools:
        logger.warning("No remote MCP tools discovered.")
        return []

    name_count = Counter(item.name for item in remote_tools)
    wrapped: list[StructuredTool] = []

    for tool_info in remote_tools:
        if name_count[tool_info.name] > 1:
            tool_name = f"{tool_info.server_name}__{tool_info.name}"
        else:
            tool_name = tool_info.name

        args_schema = _build_args_model(tool_info)

        async def _run_remote_tool(
            __server: str = tool_info.server_name,
            __name: str = tool_info.name,
            __schema: dict[str, Any] | None = tool_info.input_schema,
            **kwargs: Any,
        ) -> str:
            normalized_args = _coerce_arguments(kwargs, __schema)
            if __server == "netbox" and __name == "netbox_get_objects":
                obj_type = str(normalized_args.get("object_type", "")).strip()
                fields = normalized_args.get("fields")
                if isinstance(fields, list):
                    safe_fields = _sanitize_fields_for_object_type(obj_type, fields)
                    if safe_fields != fields:
                        normalized_args = {**normalized_args}
                        if safe_fields:
                            normalized_args["fields"] = safe_fields
                        else:
                            normalized_args.pop("fields", None)
                        logger.info(
                            "Sanitized netbox_get_objects fields for object_type=%s -> %s",
                            obj_type,
                            safe_fields,
                        )
            logger.info(
                "Executing hybrid tool: %s.%s args=%s",
                __server,
                __name,
                json.dumps(normalized_args, ensure_ascii=False),
            )
            try:
                if __server == "netbox" and __name == "netbox_search_objects":
                    query = str(normalized_args.get("query", "")).strip()
                    limit = normalized_args.get("limit", 10)
                    fields = normalized_args.get("fields")
                    if _looks_like_location_query(query):
                        direct_result = await _direct_netbox_lookup(
                            query=query,
                            limit=int(limit) if isinstance(limit, int | float | str) and str(limit).strip() else 10,
                            fields=fields if isinstance(fields, list) else None,
                        )
                        if direct_result is not None:
                            direct_result["fallback_from"] = "netbox_search_objects_preempt_location"
                            logger.info("Hybrid tool preempted location search via direct NetBox lookup.")
                            return json.dumps(direct_result, ensure_ascii=False)

                if __server == "netbox" and __name == "netbox_get_objects":
                    object_type = str(normalized_args.get("object_type", "")).strip()
                    filters = normalized_args.get("filters")
                    limit = normalized_args.get("limit", 20)
                    fields = normalized_args.get("fields")
                    query = ""
                    if object_type == "dcim.device" and isinstance(filters, dict):
                        query = str(filters.get("name__ic") or filters.get("name") or "").strip()
                    if query and _looks_like_location_query(query):
                        direct_result = await _direct_netbox_lookup(
                            query=query,
                            limit=int(limit) if isinstance(limit, int | float | str) and str(limit).strip() else 20,
                            fields=fields if isinstance(fields, list) else None,
                        )
                        if direct_result is not None:
                            direct_result["fallback_from"] = "netbox_get_objects_preempt_location"
                            logger.info("Hybrid tool preempted device name location query via direct NetBox lookup.")
                            return json.dumps(direct_result, ensure_ascii=False)

                result = await mcp_manager.call_remote_tool(
                    server_name=__server,
                    tool_name=__name,
                    arguments=normalized_args,
                )
                if __server == "netbox" and __name == "netbox_search_objects":
                    if _should_retry_netbox_search(result):
                        result = await _retry_with_netbox_get_objects(
                            manager=mcp_manager,
                            normalized_args=normalized_args,
                        )
                if __server == "netbox" and __name == "netbox_get_objects" and not result.get("ok", False):
                    object_type = str(normalized_args.get("object_type", "")).strip()
                    filters = normalized_args.get("filters")
                    limit = normalized_args.get("limit", 20)
                    fields = normalized_args.get("fields")
                    direct_result = await _direct_netbox_get_objects(
                        object_type=object_type,
                        filters=filters if isinstance(filters, dict) else None,
                        limit=int(limit) if isinstance(limit, int | float | str) and str(limit).strip() else 20,
                        fields=fields if isinstance(fields, list) else None,
                    )
                    if direct_result is not None:
                        direct_result["fallback_from"] = "netbox_get_objects"
                        result = direct_result
                if __server == "netbox" and __name == "netbox_get_object_by_id" and not result.get("ok", False):
                    object_type = str(normalized_args.get("object_type", "")).strip()
                    object_id = normalized_args.get("object_id")
                    fields = normalized_args.get("fields")
                    if isinstance(object_id, int):
                        direct_result = await _direct_netbox_get_object_by_id(
                            object_type=object_type,
                            object_id=object_id,
                            fields=fields if isinstance(fields, list) else None,
                        )
                        if direct_result is not None:
                            direct_result["fallback_from"] = "netbox_get_object_by_id"
                            result = direct_result
                logger.info(
                    "Hybrid tool returned: %s.%s -> ok=%s",
                    __server,
                    __name,
                    result.get("ok"),
                )
                return json.dumps(result, ensure_ascii=False)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Hybrid tool failed: %s.%s", __server, __name)
                if __server == "netbox" and __name == "netbox_search_objects":
                    query = str(normalized_args.get("query", "")).strip()
                    limit = normalized_args.get("limit", 10)
                    fields = normalized_args.get("fields")
                    direct_result = await _direct_netbox_lookup(
                        query=query,
                        limit=int(limit) if isinstance(limit, int | float | str) and str(limit).strip() else 10,
                        fields=fields if isinstance(fields, list) else None,
                    )
                    if direct_result is not None:
                        direct_result["fallback_from"] = f"netbox_search_objects_exception:{type(exc).__name__}"
                        return json.dumps(direct_result, ensure_ascii=False)
                if __server == "netbox" and __name == "netbox_get_objects":
                    object_type = str(normalized_args.get("object_type", "")).strip()
                    filters = normalized_args.get("filters")
                    limit = normalized_args.get("limit", 20)
                    fields = normalized_args.get("fields")
                    if object_type == "dcim.device" and isinstance(filters, dict):
                        query = str(filters.get("name__ic") or filters.get("name") or "").strip()
                        direct_result = await _direct_netbox_lookup(
                            query=query,
                            limit=int(limit) if isinstance(limit, int | float | str) and str(limit).strip() else 20,
                            fields=fields if isinstance(fields, list) else None,
                        )
                        if direct_result is not None:
                            direct_result["fallback_from"] = f"netbox_get_objects_exception:{type(exc).__name__}"
                            return json.dumps(direct_result, ensure_ascii=False)
                return json.dumps(
                    {
                        "ok": False,
                        "server_name": __server,
                        "tool_name": __name,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    ensure_ascii=False,
                )

        description = tool_info.description.strip() or f"Remote MCP tool {tool_info.name}"
        description = f"[source={tool_info.server_name}] {description}"

        wrapped_tool = StructuredTool.from_function(
            func=None,
            coroutine=_run_remote_tool,
            name=tool_name,
            description=description,
            args_schema=args_schema,
        )
        wrapped.append(wrapped_tool)

    logger.info("Hybrid MCP tools built: %d", len(wrapped))
    return wrapped
