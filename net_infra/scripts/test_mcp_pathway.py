"""MCP工具调用测试脚本。

依次完成:
1. 通过 StandardMCPManager 连接 .env 中所有非空的 MCP 端点;
2. 列出每个 server 的工具,验证拆分后清单符合预期;
3. 对每个 server 的核心工具发一组代表性入参,判断响应字段;
4. 输出聚合的 PASS / FAIL / SKIP / ERROR 报告。

用法
----
# 对全部5个server(netbox/campus/prometheus/grafana/timesfm)跑测试
python scripts/test_mcp_pathway.py

# 指定server
python scripts/test_mcp_pathway.py --servers prometheus timesfm

# 指定设备ID
python scripts/test_mcp_pathway.py --device AP-LIB-01
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any, Callable

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.mcp.client import StandardMCPManager  # noqa: E402

# ----------------------------------------------------------------------------
# 测试用例定义
# ----------------------------------------------------------------------------

Validator = Callable[[dict[str, Any]], tuple[bool, str]]


def _logical_ok(result: dict[str, Any]) -> tuple[bool, str]:
    """工具内部 ok 字段为 True 即视为通过。"""
    if result.get("ok") is True:
        return True, ""
    return False, str(result.get("error") or result)


def _has_keys(*keys: str) -> Validator:
    """检查工具响应包含指定字段(且 ok=True)。"""

    def _v(result: dict[str, Any]) -> tuple[bool, str]:
        ok, err = _logical_ok(result)
        if not ok:
            return False, err
        missing = [k for k in keys if k not in result]
        if missing:
            return False, f"missing keys: {missing}"
        return True, ""

    return _v


def _accept_either(*validators: Validator) -> Validator:
    """任一 validator 通过即视为 PASS,用于 grafana 这类无看板时也可接受空结果的场景。"""

    def _v(result: dict[str, Any]) -> tuple[bool, str]:
        errs: list[str] = []
        for vfn in validators:
            ok, err = vfn(result)
            if ok:
                return True, ""
            errs.append(err)
        return False, " | ".join(errs)

    return _v


def _shape_only(result: dict[str, Any]) -> tuple[bool, str]:
    """允许 ok=True/False,但响应必须有 ok 字段(协议级正常)。
    """
    if "ok" in result:
        return True, ""
    return False, "missing 'ok' field"


def _netbox_listlike(result: dict[str, Any]) -> tuple[bool, str]:
    """netbox-mcp-server 透传 NetBox REST API 的 List View 响应。
    NetBox List View 响应格式固定为:
        {"count": N, "next": ..., "previous": ..., "results": [...]}
    """
    if "count" in result or "results" in result:
        return True, ""
    if "detail" in result:  # NetBox 的错误响应里通常带 detail
        return False, f"netbox error: {result['detail']}"
    return False, "missing 'count'/'results' (not a NetBox list view)"


def _grafana_search_ok(result: dict[str, Any]) -> tuple[bool, str]:
    """专用于 grafana.search_dashboard / get_dashboard_url:
    严格要求 ok=True,失败时把 error 一起回带。
    """
    if result.get("ok") is True:
        return True, ""
    return False, str(result.get("error") or result)


def build_cases(device: str) -> list[dict[str, Any]]:
    """根据测试设备 ID 构建用例集。"""

    return [
        # --- campus_mcp(连通性) ---
        {
            "server": "campus",
            "tool": "ping",
            "args": {},
            "validate": _has_keys("server", "version", "timestamp"),
        },
        {
            "server": "campus",
            "tool": "echo",
            "args": {"payload": {"hello": "world", "n": 1}},
            "validate": _has_keys("received"),
        },
        # --- prometheus_mcp(指标查询) ---
        {
            "server": "prometheus",
            "tool": "get_device_metrics",
            "args": {"device_ids": [device], "window_minutes": 5},
            "validate": _has_keys("metrics"),
        },
        {
            "server": "prometheus",
            "tool": "instant_query",
            "args": {"promql": "up"},
            "validate": _has_keys("result"),
        },
        {
            "server": "prometheus",
            "tool": "range_query",
            "args": {
                "promql": f'device_packet_loss{{device_id="{device}"}}',
                "start_seconds_ago": 600,
                "end_seconds_ago": 0,
                "step_seconds": 60,
            },
            "validate": _has_keys("series"),
        },
        {
            "server": "prometheus",
            "tool": "top_n_anomaly",
            "args": {"promql": "device_packet_loss", "n": 5},
            "validate": _has_keys("items"),
        },
        # --- grafana_mcp(看板查询应该返回 ok=True;原 _shape_only 太宽容会假 PASS) ---
        {
            "server": "grafana",
            "tool": "search_dashboard",
            "args": {"query": "device", "limit": 5},
            "validate": _has_keys("items"),
        },
        {
            "server": "grafana",
            "tool": "get_dashboard_url",
            # 没有看板时 grafana 会返回 ok=False,这是合法的"无数据"响应
            # 用 _accept_either:有看板时严格 ok=True,没看板时也接受
            "args": {"device_name": device},
            "validate": _accept_either(_has_keys("dashboard_url"), _grafana_search_ok),
        },
        {
            "server": "grafana",
            "tool": "render_panel_url",
            "args": {
                "dashboard_uid": "demo-uid",
                "panel_id": 1,
                "var_device": device,
                "width": 1000,
                "height": 500,
                "from_seconds_ago": 3600,
            },
            "validate": _has_keys("render_url"),
        },
        # --- timesfm_mcp ---
        {
            "server": "timesfm",
            "tool": "forecast_metric",
            "args": {
                "device_id": device,
                "metric": "packet_loss",
                "horizon_minutes": 30,
                "freq": "1m",
            },
            "validate": _has_keys("forecast", "source", "history_points"),
        },
        {
            "server": "timesfm",
            "tool": "forecast_quantile",
            "args": {
                "device_id": device,
                "metric": "packet_loss",
                "horizon_minutes": 30,
                "freq": "1m",
                "quantiles": [0.1, 0.5, 0.9],
            },
            "validate": _has_keys("forecast", "quantiles"),
        },
        {
            "server": "timesfm",
            "tool": "detect_anomaly_window",
            "args": {
                "device_id": device,
                "metric": "packet_loss",
                "horizon_minutes": 30,
                "freq": "1m",
                "upper_quantile": 0.9,
                "threshold_override": 0.05,
            },
            "validate": _has_keys("is_anomaly", "risk_score", "threshold"),
        },
        # --- netbox(透传 NetBox REST API 原始 JSON,不带 ok 字段) ---
        {
            "server": "netbox",
            "tool": "netbox_get_objects",
            "args": {"object_type": "dcim.site", "limit": 1, "filters": {}},
            "validate": _netbox_listlike,
            "optional": True,
        },
    ]


# ----------------------------------------------------------------------------
# 执行器
# ----------------------------------------------------------------------------


def _short_dump(payload: Any, limit: int = 240) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."


async def _run_cases(
    manager: StandardMCPManager,
    cases: list[dict[str, Any]],
    target_servers: set[str] | None,
) -> list[dict[str, Any]]:
    # 列出每个 server 暴露的工具,后续按 (server, tool) 二元组判定是否 SKIP
    tools = await manager.list_remote_tools()
    by_server: dict[str, set[str]] = {}
    for t in tools:
        by_server.setdefault(t.server_name, set()).add(t.name)

    print("\n[Discovered tools]")
    if not by_server:
        print("  <none>")
    for srv in sorted(by_server):
        print(f"  - {srv}: {sorted(by_server[srv])}")
    print()

    results: list[dict[str, Any]] = []
    total = len(cases)
    for i, case in enumerate(cases, 1):
        srv: str = case["server"]
        tool: str = case["tool"]
        args: dict[str, Any] = case["args"]
        validate: Validator = case["validate"]
        optional: bool = bool(case.get("optional"))
        case_id = f"{srv}.{tool}"

        if target_servers is not None and srv not in target_servers:
            print(f"[{i:>2d}/{total}] {case_id} SKIP (server filtered out)")
            results.append({"case": case_id, "status": "SKIP", "reason": "filtered"})
            continue

        registered_tools = by_server.get(srv)
        if registered_tools is None:
            print(f"[{i:>2d}/{total}] {case_id} SKIP (server not connected)")
            results.append({"case": case_id, "status": "SKIP", "reason": "server offline"})
            continue
        if tool not in registered_tools:
            status = "SKIP" if optional else "FAIL"
            print(f"[{i:>2d}/{total}] {case_id} {status} (tool not exposed)")
            results.append({"case": case_id, "status": status, "reason": "tool missing"})
            continue

        print(f"[{i:>2d}/{total}] {case_id} args={_short_dump(args, 160)}")
        t0 = time.perf_counter()
        try:
            envelope = await manager.call_remote_tool(
                server_name=srv, tool_name=tool, arguments=args,
            )
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            dt_ms = (time.perf_counter() - t0) * 1000
            print(f"        ERROR ({dt_ms:.0f}ms) {type(exc).__name__}: {exc}")
            results.append(
                {"case": case_id, "status": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}
            )
            continue
        dt_ms = (time.perf_counter() - t0) * 1000

        if not envelope.get("ok"):
            text = envelope.get("text") or envelope.get("content")
            print(f"        FAIL  ({dt_ms:.0f}ms) protocol error: {_short_dump(text)}")
            results.append({"case": case_id, "status": "FAIL", "reason": "protocol error"})
            continue

        inner = envelope.get("structured_content")
        if not isinstance(inner, dict):
            # 部分 FastMCP 版本将基础类型放在 text 里,这里宽容处理
            text_val = envelope.get("text", "")
            try:
                inner = json.loads(text_val) if isinstance(text_val, str) and text_val.strip() else {}
                if not isinstance(inner, dict):
                    inner = {"_raw": inner}
            except json.JSONDecodeError:
                inner = {"_raw": text_val}

        ok, err = validate(inner)
        if ok:
            extra = ""
            if "source" in inner:
                extra += f" source={inner['source']}"
            if "history_points" in inner:
                extra += f" history={inner['history_points']}"
            if "forecast" in inner and isinstance(inner["forecast"], list):
                fc = inner["forecast"]
                if fc:
                    extra += f" forecast[0:3]={[round(x, 5) for x in fc[:3]]}"
            if "is_anomaly" in inner:
                extra += f" anomaly={inner['is_anomaly']} risk={round(inner.get('risk_score', 0), 3)}"
            print(f"        PASS  ({dt_ms:.0f}ms){extra}")
            results.append({"case": case_id, "status": "PASS", "latency_ms": dt_ms})
        else:
            print(f"        FAIL  ({dt_ms:.0f}ms) {err}")
            print(f"               body: {_short_dump(inner)}")
            results.append({"case": case_id, "status": "FAIL", "reason": err})

    return results


def _print_summary(results: list[dict[str, Any]]) -> int:
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    total = len(results)
    print("\n" + "=" * 70)
    print(f"Summary: total={total}  PASS={counts['PASS']}  FAIL={counts['FAIL']}  "
          f"ERROR={counts['ERROR']}  SKIP={counts['SKIP']}")
    print("=" * 70)
    bad = [r for r in results if r["status"] in ("FAIL", "ERROR")]
    if bad:
        print("Non-PASS details:")
        for r in bad:
            print(f"  [{r['status']}] {r['case']}: {r.get('reason', '')}")

    return 0 if counts["FAIL"] == 0 and counts["ERROR"] == 0 else 1


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


async def _async_main(args: argparse.Namespace) -> int:
    print("=" * 70)
    print("  CampusNet MCP Pathway Test")
    print(f"  Test device: {args.device}")
    print("=" * 70)

    manager = StandardMCPManager.from_settings()
    if not manager.endpoints:
        print("[ERROR] 没有任何 MCP 端点配置,请检查 .env 中 *_MCP_SSE_URL", file=sys.stderr)
        return 2

    target = set(args.servers) if args.servers else None
    if target:
        # 只过滤 endpoints 列表,manager 内部仍按需懒连接
        manager.endpoints = [ep for ep in manager.endpoints if ep.name in target]
        if not manager.endpoints:
            print(f"[ERROR] --servers {sorted(target)} 与已配置端点无交集", file=sys.stderr)
            return 2

    print(f"Targeting endpoints: {[ep.name for ep in manager.endpoints]}")

    try:
        await manager.connect()
        cases = build_cases(args.device)
        results = await _run_cases(manager, cases, target)
    finally:
        try:
            await manager.close()
        except Exception:  # noqa: BLE001
            pass

    return _print_summary(results)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="端到端测试拆分后的 MCP Server 工具调用通路。",
    )
    parser.add_argument(
        "--device",
        default="AP-EXAM-301",
        help="测试用设备 ID(应已通过 inject_prometheus_test_data.py 注入数据,默认 AP-EXAM-301)",
    )
    parser.add_argument(
        "--servers",
        nargs="+",
        choices=["netbox", "campus", "prometheus", "grafana", "timesfm"],
        default=None,
        help="只测试指定 server(空 = 全部已配置端点)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        rc = asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
