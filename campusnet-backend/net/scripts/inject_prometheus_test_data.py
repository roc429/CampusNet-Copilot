"""向 Prometheus(经Pushgateway)注入合成测试时序数据的脚本。
用法
----
# 一次性快速注入(只推一轮)
python scripts/inject_prometheus_test_data.py --once

# 持续推送10分钟,每5秒一轮(给TimesFM累积上下文)
python scripts/inject_prometheus_test_data.py --duration 600 --interval 5

# 指定不同Pushgateway(Prometheus的API)
python scripts/inject_prometheus_test_data.py --pushgateway http://1.2.3.4:9091 \\
    --devices AP-A3-2F-01 SW-CORE-01

# 模拟某台设备故障(packet_loss飙升)
python scripts/inject_prometheus_test_data.py --duration 300 --fault-device AP-LIB-3F-02
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import random
import sys
import time

import httpx

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from mcp_servers._common.http import make_async_client  # noqa: E402

DEFAULT_PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://localhost:9091")
DEFAULT_JOB = "campusnet_telemetry"

# 默认设备清单
DEVICES: list[dict[str, str]] = [
    {"id": "AP-A3-2F-01", "type": "ap", "building": "A3", "floor": "2F"},
    {"id": "AP-LIB-3F-02", "type": "ap", "building": "LIB", "floor": "3F"},
    {"id": "SW-CORE-01", "type": "switch", "building": "CORE", "floor": "1F"},
    {"id": "SC-CORE-01", "type": "switch", "building": "CORE", "floor": "1F"},
]


def _gen_metrics(device: dict[str, str], t: float, fault: bool = False) -> dict[str, float]:
    """根据时间生成一个伪指标。

    Args:
        device: 设备元数据。
        t: 当前时间戳(秒)。
        fault: 是否注入故障(packet_loss 飙升、cpu 爆表)。
    """

    # 用一天周期的正弦波模拟昼夜负载(峰值约在 14:00 ~ 18:00)
    phase = (t % 86_400) / 86_400 * 2 * math.pi
    base_load = 0.5 + 0.4 * math.sin(phase - math.pi / 4)  # 0.1 ~ 0.9
    noise = random.gauss(0, 0.05)

    if device["type"] == "ap":
        connections = max(0, int(80 + 60 * base_load + random.gauss(0, 8)))
        cpu_load = max(0.0, min(1.0, 0.30 + 0.50 * base_load + noise))
        packet_loss = max(0.0, 0.005 + 0.06 * base_load + abs(random.gauss(0, 0.01)))
    else:  # switch
        connections = max(0, int(400 + 300 * base_load + random.gauss(0, 30)))
        cpu_load = max(0.0, min(1.0, 0.20 + 0.60 * base_load + noise))
        packet_loss = max(0.0, 0.003 + 0.04 * base_load + abs(random.gauss(0, 0.005)))

    if fault:
        packet_loss = min(0.50, packet_loss + 0.20 + random.uniform(0, 0.15))
        cpu_load = min(1.0, cpu_load + 0.3)
        connections = int(connections * 1.6)

    # 链路侧的 if_in/out_octets:每秒字节数,GBE 上限 ~125MB/s
    if_in_octets = int(40_000_000 * base_load + random.uniform(-2e6, 2e6))
    if_out_octets = int(35_000_000 * base_load + random.uniform(-2e6, 2e6))

    return {
        "device_connections": float(connections),
        "device_cpu_load": float(cpu_load),
        "device_packet_loss": float(packet_loss),
        "if_in_octets": float(if_in_octets),
        "if_out_octets": float(if_out_octets),
    }


def _build_pushgateway_body(device: dict[str, str], metrics: dict[str, float]) -> str:
    """生成 Pushgateway 兼容的body。

    每行格式:  <metric_name>{<labels>} <value>
    Pushgateway 要求每个 metric_name 至少一行。
    """

    label_str = (
        f'device_id="{device["id"]}",'
        f'device_type="{device["type"]}",'
        f'building="{device["building"]}",'
        f'floor="{device["floor"]}"'
    )

    lines: list[str] = []
    for metric_name, value in metrics.items():
        lines.append(f"# TYPE {metric_name} gauge")
        lines.append(f"{metric_name}{{{label_str}}} {value}")
    # Pushgateway 文本协议要求以换行结尾
    return "\n".join(lines) + "\n"


async def _push_one_round(
    client: httpx.AsyncClient,
    pushgateway_url: str,
    job: str,
    devices: list[dict[str, str]],
    fault_device: str | None,
    verbose: bool = True,
) -> tuple[int, int]:
    """对所有设备推送一轮指标,返回 (成功数, 失败数)。"""

    ok_count = 0
    err_count = 0
    now = time.time()
    for device in devices:
        is_faulty = fault_device is not None and device["id"] == fault_device
        metrics = _gen_metrics(device, now, fault=is_faulty)
        body = _build_pushgateway_body(device, metrics)

        # PUT: 替换该 grouping_key 下所有 metrics(干净状态)
        url = (
            f"{pushgateway_url.rstrip('/')}"
            f"/metrics/job/{job}/instance/{device['id']}"
        )
        try:
            resp = await client.put(
                url,
                content=body,
                headers={"Content-Type": "text/plain; version=0.0.4"},
            )
            if resp.status_code >= 400:
                err_count += 1
                if verbose:
                    print(
                        f"  [WARN] {device['id']} -> HTTP {resp.status_code}: "
                        f"{resp.text[:120]}"
                    )
            else:
                ok_count += 1
                if verbose:
                    flag = " *FAULT*" if is_faulty else ""
                    print(
                        f"  [OK]   {device['id']:<14}{flag} "
                        f"loss={metrics['device_packet_loss']:.4f} "
                        f"cpu={metrics['device_cpu_load']:.3f} "
                        f"conn={int(metrics['device_connections']):>4d}"
                    )
        except httpx.HTTPError as exc:
            err_count += 1
            if verbose:
                print(f"  [ERR]  {device['id']} -> {type(exc).__name__}: {exc}")
    return ok_count, err_count


async def _check_pushgateway(client: httpx.AsyncClient, pushgateway_url: str) -> bool:
    """健康检查。"""

    try:
        resp = await client.get(f"{pushgateway_url.rstrip('/')}/-/healthy", timeout=3)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


async def _async_main(args: argparse.Namespace) -> int:
    devices = DEVICES
    if args.devices:
        wanted = set(args.devices)
        devices = [d for d in DEVICES if d["id"] in wanted]
        if not devices:
            print(f"[ERROR] --devices 指定的设备未在内置清单中: {args.devices}", file=sys.stderr)
            print(f"        内置清单: {[d['id'] for d in DEVICES]}", file=sys.stderr)
            return 2

    if args.fault_device and args.fault_device not in {d["id"] for d in devices}:
        print(
            f"[ERROR] --fault-device {args.fault_device} 不在被注入的设备列表中",
            file=sys.stderr,
        )
        return 2

    print("=" * 70)
    print(f"  Pushgateway     : {args.pushgateway}")
    print(f"  Job             : {args.job}")
    print(f"  Devices         : {[d['id'] for d in devices]}")
    print(f"  Fault device    : {args.fault_device or '<none>'}")
    print(f"  Mode            : {'once' if args.once else f'continuous {args.duration}s @ {args.interval}s'}")
    print("=" * 70)

    async with make_async_client(timeout_seconds=10.0) as client:
        # 健康检查
        if not await _check_pushgateway(client, args.pushgateway):
            print(
                f"[ERROR] Pushgateway 健康检查失败: {args.pushgateway}/-/healthy 不通",
                file=sys.stderr,
            )
            print("        请确认 docker-compose 已启动 pushgateway 服务。", file=sys.stderr)
            print(
                "        若浏览器能打开 /-/healthy 但本脚本失败,通常是系统代理(Clash/V2Ray)劫持了 127.0.0.1。",
                file=sys.stderr,
            )
            print(
                "        当前 trust_env 已根据 DISABLE_ENV_PROXY=true 关闭;若仍失败,"
                "尝试 set HTTP_PROXY= && set HTTPS_PROXY= 后重试。",
                file=sys.stderr,
            )
            return 3
        print(f"[OK] Pushgateway healthy.\n")

        if args.once:
            print(f"[round 1] {time.strftime('%H:%M:%S')}")
            ok, err = await _push_one_round(
                client, args.pushgateway, args.job, devices, args.fault_device,
            )
            print(f"\nDone. ok={ok} err={err}")
            return 0 if err == 0 else 4

        end_at = time.time() + args.duration
        round_n = 0
        total_ok = 0
        total_err = 0
        try:
            while time.time() < end_at:
                round_n += 1
                remaining = max(0, int(end_at - time.time()))
                print(f"[round {round_n:>3d}] {time.strftime('%H:%M:%S')} (remaining {remaining}s)")
                ok, err = await _push_one_round(
                    client, args.pushgateway, args.job, devices, args.fault_device,
                )
                total_ok += ok
                total_err += err
                # 最后一轮不再 sleep,加快收尾
                if time.time() < end_at:
                    await asyncio.sleep(args.interval)
        except asyncio.CancelledError:
            print("\n[CANCEL] interrupted, flushing.")
            raise
        except KeyboardInterrupt:
            print("\n[CTRL-C] interrupted.")

        print("\n" + "=" * 70)
        print(f"Summary: rounds={round_n} ok_pushes={total_ok} err_pushes={total_err}")
        print("=" * 70)
        return 0 if total_err == 0 else 4


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="向 Prometheus(经 Pushgateway)注入合成校园网测试数据。",
    )
    parser.add_argument(
        "--pushgateway",
        default=DEFAULT_PUSHGATEWAY_URL,
        help=f"Pushgateway 基础地址(默认 {DEFAULT_PUSHGATEWAY_URL})",
    )
    parser.add_argument(
        "--job",
        default=DEFAULT_JOB,
        help=f"Pushgateway grouping_key 中的 job 名(默认 {DEFAULT_JOB})",
    )
    parser.add_argument(
        "--devices",
        nargs="+",
        default=None,
        metavar="DEVICE_ID",
        help="只对这些设备 ID 推送(空 = 全部)",
    )
    parser.add_argument(
        "--fault-device",
        default=None,
        metavar="DEVICE_ID",
        help="对该设备注入故障(packet_loss 飙升),用于测试 detect_anomaly_window",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--once",
        action="store_true",
        help="只推一轮就退出",
    )
    mode.add_argument(
        "--duration",
        type=int,
        default=120,
        help="持续推送总秒数,默认 120 秒",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="每轮推送间隔秒数,默认 5 秒",
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
