# -*- coding: utf-8 -*-
"""
telemetry_to_pushgateway.py

作用：
1. 读取 Ryu 生成的 telemetry.csv。
2. 根据 dpid + port 映射到统一 device_id。
3. 把 load / loss 转成 Prometheus 指标。
4. 推送到 Pushgateway。
5. Prometheus 再从 Pushgateway 抓取指标。

链路：
Ryu -> telemetry.csv -> Pushgateway -> Prometheus -> TimesFM
"""

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Dict, Tuple, Any

import requests

CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from device_map import DEVICE_MAP, AP_DEVICE_IDS


DEFAULT_TELEMETRY = "/home/jowin/Desktop/neta/phase2/data/telemetry.csv"
DEFAULT_PUSHGATEWAY = "http://127.0.0.1:9091/metrics/job/campusnet"


def build_device_port_map() -> Dict[Tuple[int, int], Dict[str, Any]]:
    """
    从 device_map.py 中生成：
    (dpid, port) -> device_id

    例如：
    (6, 1) -> AP-EXAM-302
    """
    result = {}

    for device_id in AP_DEVICE_IDS:
        device = DEVICE_MAP[device_id]

        key = (
            int(device["dpid"]),
            int(device["port"])
        )

        result[key] = {
            "device_id": device_id,
            "device_name": device.get("name", device_id),
            "zone_id": device.get("zone_id", ""),
            "area_id": device.get("area_id", ""),
            "role": "ap"
        }

    return result


DEVICE_PORT_MAP = build_device_port_map()


def read_latest_metrics(telemetry_file: str) -> Dict[Tuple[int, int], Dict[str, Any]]:
    """
    读取 telemetry.csv，并且只保留每个 AP 端口的最新一条记录。
    """
    path = Path(telemetry_file).expanduser()

    if not path.exists():
        raise FileNotFoundError("找不到 telemetry.csv: {}".format(path))

    latest = {}

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        required = {
            "timestamp",
            "dpid",
            "port",
            "load",
            "loss"
        }

        if reader.fieldnames is None:
            raise ValueError("telemetry.csv 没有表头")

        missing = required - set(reader.fieldnames)

        if missing:
            raise ValueError("telemetry.csv 缺少字段: {}".format(sorted(missing)))

        for row in reader:
            try:
                dpid = int(float(row["dpid"]))
                port = int(float(row["port"]))
                ts = float(row["timestamp"])
                load = float(row["load"])
                loss = float(row["loss"])
            except Exception:
                continue

            key = (dpid, port)

            if key not in DEVICE_PORT_MAP:
                continue

            old = latest.get(key)

            if old is None or ts > old["timestamp"]:
                latest[key] = {
                    "timestamp": ts,
                    "dpid": dpid,
                    "port": port,
                    "load": load,
                    "loss": loss
                }

    return latest


def build_prometheus_text(latest: Dict[Tuple[int, int], Dict[str, Any]]) -> str:
    """
    构造 Pushgateway 接收的 Prometheus 文本格式。

    示例：
    ap_load{device_id="AP-EXAM-302",dpid="6",port="1"} 0.52
    ap_loss{device_id="AP-EXAM-302",dpid="6",port="1"} 0.01
    """
    lines = []

    lines.append("# HELP ap_load AP load ratio exported from Ryu telemetry")
    lines.append("# TYPE ap_load gauge")

    for key, metric in sorted(latest.items()):
        device = DEVICE_PORT_MAP[key]

        labels = (
            'device_id="{device_id}",'
            'device_name="{device_name}",'
            'zone_id="{zone_id}",'
            'area_id="{area_id}",'
            'role="{role}",'
            'dpid="{dpid}",'
            'port="{port}"'
        ).format(
            device_id=device["device_id"],
            device_name=device["device_name"],
            zone_id=device["zone_id"],
            area_id=device["area_id"],
            role=device["role"],
            dpid=metric["dpid"],
            port=metric["port"]
        )

        lines.append(
            "ap_load{{{}}} {}".format(
                labels,
                metric["load"]
            )
        )

    lines.append("# HELP ap_loss AP packet loss ratio exported from Ryu telemetry")
    lines.append("# TYPE ap_loss gauge")

    for key, metric in sorted(latest.items()):
        device = DEVICE_PORT_MAP[key]

        labels = (
            'device_id="{device_id}",'
            'device_name="{device_name}",'
            'zone_id="{zone_id}",'
            'area_id="{area_id}",'
            'role="{role}",'
            'dpid="{dpid}",'
            'port="{port}"'
        ).format(
            device_id=device["device_id"],
            device_name=device["device_name"],
            zone_id=device["zone_id"],
            area_id=device["area_id"],
            role=device["role"],
            dpid=metric["dpid"],
            port=metric["port"]
        )

        lines.append(
            "ap_loss{{{}}} {}".format(
                labels,
                metric["loss"]
            )
        )

    return "\n".join(lines) + "\n"


def push_metrics(pushgateway_url: str, text: str) -> Dict[str, Any]:
    """
    推送指标到 Pushgateway。

    PUT 表示替换当前 job=campusnet 下的指标。
    """
    r = requests.put(
        pushgateway_url,
        data=text.encode("utf-8"),
        headers={
            "Content-Type": "text/plain; version=0.0.4"
        },
        timeout=5
    )

    if r.status_code not in (200, 202):
        raise RuntimeError(
            "Pushgateway 写入失败: status={} body={}".format(
                r.status_code,
                r.text
            )
        )

    return {
        "ok": True,
        "status_code": r.status_code
    }


def main():
    parser = argparse.ArgumentParser(description="Ryu telemetry.csv -> Pushgateway")

    parser.add_argument(
        "--telemetry",
        default=DEFAULT_TELEMETRY,
        help="Ryu telemetry.csv 路径"
    )

    parser.add_argument(
        "--pushgateway",
        default=DEFAULT_PUSHGATEWAY,
        help="Pushgateway metrics URL"
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="推送间隔，单位秒"
    )

    args = parser.parse_args()

    print("========== telemetry_to_pushgateway 启动 ==========")
    print("telemetry:", args.telemetry)
    print("pushgateway:", args.pushgateway)
    print("interval:", args.interval)

    while True:
        try:
            latest = read_latest_metrics(args.telemetry)
            text = build_prometheus_text(latest)
            result = push_metrics(args.pushgateway, text)

            device_ids = [
                DEVICE_PORT_MAP[key]["device_id"]
                for key in latest.keys()
            ]

            print(
                "[OK] pushed_devices={} devices={} status={}".format(
                    len(latest),
                    ",".join(device_ids),
                    result["status_code"]
                )
            )

        except Exception as e:
            print("[ERROR]", e)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()