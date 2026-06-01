# -*- coding: utf-8 -*-
"""
mininet_topology_runner.py

作用：
1. 读取 topology_seed.json。
2. 自动生成 Mininet 拓扑。
3. 连接外部 Ryu Controller。
4. 模拟 AP 负载。
5. 将 AP 负载写入 Prometheus Pushgateway。
6. 支持正常负载、告警负载、异常负载。
7. 支持 dry-run、emit-only、run 三种模式。
8. 使用短 Mininet 节点名，避免 Linux ifname 超长。
9. 生成 mininet_node_map.json，保存短节点名和真实 device_id 的映射。

核心原则：
- 业务统一 ID：device_id，例如 AP-EXAM-302。
- Mininet 内部节点名：s1/s2/s3、h1/h2。
- 不允许把 h1/h2/s3 当成业务 device_id。
- Prometheus / TimesFM / 前端 / 主动防御 全部继续使用 device_id。

推荐启动顺序：

1. 启动 Ryu：

cd /home/jowin/Desktop/neta
ryu-manager --ofp-tcp-listen-port 6633 --wsapi-port 8080 phase2/flow_ai.py

2. 启动 Pushgateway：

prometheus-pushgateway --web.listen-address=":9091"

3. 启动 Prometheus：

cd /home/jowin/Desktop/neta
prometheus --config.file=prometheus.yml --storage.tsdb.path=phase2/prometheus_data

4. 启动动态拓扑：

cd ~/mininet

sudo PYTHONPATH=$HOME/mininet \
/usr/bin/python3 /home/jowin/Desktop/neta/phase2/topology/mininet_topology_runner.py \
  --seed /home/jowin/Desktop/neta/phase2/topology/topology_seed.json \
  --mode run \
  --duration 0 \
  --interval 5 \
  --anomaly-device AP-EXAM-302 \
  --anomaly-after 20 \
  --print-payload
"""

import argparse
import json
import os
import random
import re
import signal
import socket
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


DEFAULT_SEED = "phase2/topology/topology_seed.json"
DEFAULT_CONTROLLER_IP = "127.0.0.1"
DEFAULT_CONTROLLER_PORT = 6633

DEFAULT_NODE_MAP_OUTPUT = "/home/jowin/Desktop/neta/phase2/data/mininet_node_map.json"

STOP_REQUESTED = False


def handle_stop_signal(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    print("\n[runner] stop requested, cleaning up...")


signal.signal(signal.SIGINT, handle_stop_signal)
signal.signal(signal.SIGTERM, handle_stop_signal)


# ============================================================
# 基础工具
# ============================================================

def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Dict[str, Any]) -> None:
    parent = os.path.dirname(path)

    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_dpid(value: Any) -> str:
    """
    Mininet / OVS 要求 dpid 是 16 位十六进制字符串。

    seed 里可能是：
    "6"
    "10"

    这里统一转成：
    0000000000000006
    000000000000000a
    """
    text = str(value).strip()

    try:
        number = int(text, 10)
    except Exception:
        number = abs(hash(text)) % 1000000

    if number <= 0:
        number = 1

    return "{:016x}".format(number)


def short_text(value: Any, max_len: int = 12) -> str:
    text = str(value)
    text = re.sub(r"[^a-zA-Z0-9_]", "_", text)
    return text[:max_len]


def check_port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def import_mininet_modules():
    """
    延迟导入 Mininet。

    dry-run / emit-only 不需要 Mininet。
    run 模式才需要。
    """
    try:
        from mininet.net import Mininet
        from mininet.topo import Topo
        from mininet.node import RemoteController, OVSKernelSwitch
        from mininet.link import TCLink
        from mininet.log import setLogLevel
        from mininet.cli import CLI

        return Mininet, Topo, RemoteController, OVSKernelSwitch, TCLink, setLogLevel, CLI

    except Exception as e:
        raise RuntimeError(
            "Cannot import Mininet Python modules. "
            "Please install Mininet and run with system python3, not venv python.\n\n"
            "Recommended:\n"
            "cd ~/mininet\n"
            "sudo PYTHONPATH=$HOME/mininet "
            "/usr/bin/python3 /home/jowin/Desktop/neta/phase2/topology/mininet_topology_runner.py "
            "--seed /home/jowin/Desktop/neta/phase2/topology/topology_seed.json --mode run\n\n"
            "Original error: {}".format(e)
        )


# ============================================================
# seed 解析
# ============================================================

def get_pushgateway_url(seed: Dict[str, Any]) -> str:
    return (
        seed.get("prometheus", {}).get("pushgateway_url")
        or os.environ.get("PUSHGATEWAY_URL")
        or "http://127.0.0.1:9091"
    ).rstrip("/")


def get_pushgateway_job(seed: Dict[str, Any]) -> str:
    return (
        seed.get("prometheus", {}).get("job")
        or os.environ.get("PUSHGATEWAY_JOB")
        or "campusnet"
    )


def get_traffic_config(seed: Dict[str, Any]) -> Dict[str, Any]:
    return seed.get("traffic", {})


def get_range(
    seed: Dict[str, Any],
    name: str,
    default_low: float,
    default_high: float,
) -> Tuple[float, float]:
    traffic = get_traffic_config(seed)
    value = traffic.get(name, [default_low, default_high])

    try:
        low = float(value[0])
        high = float(value[1])
    except Exception:
        low = default_low
        high = default_high

    return low, high


def extract_aps(seed: Dict[str, Any]) -> List[Dict[str, Any]]:
    aps: List[Dict[str, Any]] = []

    topology = seed.get("topology", {})
    areas = topology.get("areas", [])

    for area in areas:
        area_id = str(area.get("area_id", "unknown"))
        zone_id = str(area.get("zone_id", "unknown"))
        area_name = str(area.get("area_name", area_id))

        for ap in area.get("aps", []):
            item = dict(ap)
            item["area_id"] = area_id
            item["zone_id"] = zone_id
            item["area_name"] = area_name
            aps.append(item)

    return aps


def validate_seed(seed: Dict[str, Any]) -> None:
    if "topology" not in seed:
        raise ValueError("topology_seed.json 缺少 topology 字段")

    if "areas" not in seed["topology"]:
        raise ValueError("topology_seed.json 缺少 topology.areas 字段")

    aps = extract_aps(seed)

    if not aps:
        raise ValueError("topology_seed.json 中没有任何 AP")


def print_seed_summary(seed_path: str, seed: Dict[str, Any]) -> None:
    validate_seed(seed)

    project = seed.get("project", "unknown")
    core = seed.get("topology", {}).get("core", {}).get("name", "core")
    areas = seed.get("topology", {}).get("areas", [])
    aps = extract_aps(seed)

    print("[run] seed loaded successfully: {}".format(seed_path))
    print("[topology] project: {}".format(project))
    print("[topology] core: {}".format(core))
    print("[topology] areas: {}".format(len(areas)))
    print("[topology] aps: {}".format(len(aps)))

    for ap in aps:
        print(
            "  - device_id={device_id}, ip={management_ip}, name={device_name}, area={area_id}, zone={zone_id}, "
            "dpid={dpid}, port={port}, clients={clients}".format(
                device_id=ap.get("device_id", ""),
                management_ip=ap.get("management_ip", ""),
                device_name=ap.get("device_name", ""),
                area_id=ap.get("area_id", ""),
                zone_id=ap.get("zone_id", ""),
                dpid=ap.get("dpid", ""),
                port=ap.get("port", ""),
                clients=ap.get("clients", ""),
            )
        )


# ============================================================
# node map
# ============================================================

def empty_node_map(seed_path: str = "") -> Dict[str, Any]:
    return {
        "seed_path": seed_path,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "controller": {
            "type": "RemoteController",
            "ip": DEFAULT_CONTROLLER_IP,
            "port": DEFAULT_CONTROLLER_PORT,
        },
        "core": {
            "switch_node": "s1",
            "device_id": "OF-CORE-01",
            "dpid": make_dpid(1),
        },
        "area_switch_map": {},
        "ap_switch_map": {},
        "switch_device_map": {},
        "device_switch_map": {},
        "host_parent_device_map": {},
        "device_host_map": {},
        "host_ip_map": {},
        "devices": {},
    }


def add_device_to_node_map(
    node_map: Dict[str, Any],
    device_id: str,
    switch_node: str,
    dpid: str,
    ap: Dict[str, Any],
) -> None:
    node_map["ap_switch_map"][device_id] = {
        "switch_node": switch_node,
        "device_id": device_id,
        "dpid": dpid,
        "management_ip": str(ap.get("management_ip", "")),
        "device_name": str(ap.get("device_name", device_id)),
        "area_id": str(ap.get("area_id", "")),
        "zone_id": str(ap.get("zone_id", "")),
        "role": str(ap.get("role", "ap")),
        "port": str(ap.get("port", "")),
    }

    node_map["switch_device_map"][switch_node] = device_id
    node_map["device_switch_map"][device_id] = switch_node

    node_map["devices"][device_id] = {
        "device_id": device_id,
        "device_name": str(ap.get("device_name", device_id)),
        "management_ip": str(ap.get("management_ip", "")),
        "area_id": str(ap.get("area_id", "")),
        "zone_id": str(ap.get("zone_id", "")),
        "role": str(ap.get("role", "ap")),
        "dpid": str(ap.get("dpid", "")),
        "normalized_dpid": dpid,
        "port": str(ap.get("port", "")),
        "switch_node": switch_node,
        "host_nodes": [],
    }


def add_host_to_node_map(
    node_map: Dict[str, Any],
    host_name: str,
    parent_device_id: str,
    host_ip: str,
) -> None:
    node_map["host_parent_device_map"][host_name] = parent_device_id
    node_map["host_ip_map"][host_name] = host_ip

    if parent_device_id not in node_map["device_host_map"]:
        node_map["device_host_map"][parent_device_id] = []

    node_map["device_host_map"][parent_device_id].append(host_name)

    if parent_device_id in node_map["devices"]:
        node_map["devices"][parent_device_id]["host_nodes"].append(host_name)


def print_node_map_summary(node_map: Dict[str, Any]) -> None:
    print("[mapping] switch -> device_id")
    for switch_node, device_id in sorted(node_map.get("switch_device_map", {}).items()):
        print("  - {} -> {}".format(switch_node, device_id))

    print("[mapping] host -> parent device_id")
    for host_node, device_id in sorted(node_map.get("host_parent_device_map", {}).items()):
        host_ip = node_map.get("host_ip_map", {}).get(host_node, "")
        print("  - {} -> {} ip={}".format(host_node, device_id, host_ip))


# ============================================================
# Prometheus Pushgateway 写入
# ============================================================

def escape_label_value(value: Any) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    text = text.replace("\n", "\\n")
    return text


def build_prometheus_payload(seed: Dict[str, Any], values: Dict[str, float]) -> str:
    """
    Prometheus 里仍然使用真实业务 device_id。

    注意：
    - 不使用 h1/h2/s3 作为 device_id。
    - h1/h2/s3 只是 Mininet 内部节点名。
    """
    lines: List[str] = []

    lines.append("# HELP ap_load AP load ratio exported from Mininet topology runner")
    lines.append("# TYPE ap_load gauge")

    aps = extract_aps(seed)

    for ap in aps:
        device_id = str(ap.get("device_id", "unknown"))
        value = float(values.get(device_id, 0.0))

        labels = {
            "area_id": str(ap.get("area_id", "")),
            "zone_id": str(ap.get("zone_id", "")),
            "device_id": str(ap.get("device_id", "")),
            "device_name": str(ap.get("device_name", "")),
            "management_ip": str(ap.get("management_ip", "")),
            "dpid": str(ap.get("dpid", "")),
            "port": str(ap.get("port", "")),
            "role": str(ap.get("role", "ap")),
        }

        label_text = ",".join(
            '{}="{}"'.format(k, escape_label_value(v))
            for k, v in labels.items()
        )

        lines.append('ap_load{{{}}} {}'.format(label_text, value))

    return "\n".join(lines) + "\n"


def push_to_gateway(
    pushgateway_url: str,
    job: str,
    payload: str,
    timeout: int = 5,
) -> None:
    url = "{}/metrics/job/{}".format(pushgateway_url.rstrip("/"), job)

    r = requests.put(
        url,
        data=payload.encode("utf-8"),
        headers={"Content-Type": "text/plain; version=0.0.4; charset=utf-8"},
        timeout=timeout,
    )

    if r.status_code not in (200, 202):
        raise RuntimeError(
            "Pushgateway write failed. status={}, text={}".format(
                r.status_code,
                r.text[:300],
            )
        )


# ============================================================
# 负载模拟
# ============================================================

def generate_ap_loads(
    seed: Dict[str, Any],
    anomaly_device: Optional[str],
    anomaly_started: bool,
) -> Dict[str, float]:
    normal_low, normal_high = get_range(seed, "normal_load_range", 0.25, 0.55)
    warning_low, warning_high = get_range(seed, "warning_load_range", 0.65, 0.78)
    anomaly_low, anomaly_high = get_range(seed, "anomaly_load_range", 0.92, 1.0)

    values: Dict[str, float] = {}

    for ap in extract_aps(seed):
        device_id = str(ap.get("device_id", ""))

        if anomaly_device and device_id == anomaly_device:
            if anomaly_started:
                value = random.uniform(anomaly_low, anomaly_high)
            else:
                value = random.uniform(warning_low, warning_high)
        else:
            value = random.uniform(normal_low, normal_high)

        value = max(0.0, min(1.0, value))
        values[device_id] = round(value, 6)

    return values


def run_metric_loop(
    seed: Dict[str, Any],
    duration: int,
    interval: int,
    anomaly_device: Optional[str],
    anomaly_after: int,
    print_payload: bool,
) -> None:
    pushgateway_url = get_pushgateway_url(seed)
    job = get_pushgateway_job(seed)

    print("[pushgateway] url: {}".format(pushgateway_url))
    print("[pushgateway] job: {}".format(job))

    start_time = time.time()
    tick = 0

    while not STOP_REQUESTED:
        now = time.time()
        elapsed = now - start_time

        if duration > 0 and elapsed >= duration:
            print("[runner] duration reached: {} seconds".format(duration))
            break

        anomaly_started = False
        if anomaly_device:
            anomaly_started = elapsed >= anomaly_after

        values = generate_ap_loads(
            seed=seed,
            anomaly_device=anomaly_device,
            anomaly_started=anomaly_started,
        )

        payload = build_prometheus_payload(seed, values)

        if print_payload:
            print(
                "\n========== prometheus payload tick={} elapsed={:.1f}s ==========".format(
                    tick,
                    elapsed,
                )
            )
            print(payload.rstrip())

        try:
            push_to_gateway(
                pushgateway_url=pushgateway_url,
                job=job,
                payload=payload,
            )
            print(
                "[push] ok tick={} elapsed={:.1f}s anomaly_started={} values={}".format(
                    tick,
                    elapsed,
                    anomaly_started,
                    values,
                )
            )
        except Exception as e:
            print("[push] failed: {}".format(e))

        tick += 1
        time.sleep(max(1, interval))


# ============================================================
# Mininet 动态拓扑
# ============================================================

def build_mininet_topology_class(seed: Dict[str, Any], node_map: Dict[str, Any]):
    """
    根据 seed 生成 Mininet Topo class。

    重点：
    1. switch 全部使用短名 s1、s2、s3。
    2. switch 显式设置 dpid，防止 Mininet 推导 dpid 失败。
    3. host 全部使用短名 h1、h2、h3，防止 hxxx-eth0 超过 Linux ifname 限制。
    4. 真实业务 ID 保存在 node_map，不丢失。
    """
    (
        Mininet,
        Topo,
        RemoteController,
        OVSKernelSwitch,
        TCLink,
        setLogLevel,
        CLI,
    ) = import_mininet_modules()

    class CampusSeedTopo(Topo):
        def build(self):
            # core switch，固定 s1
            core_switch = self.addSwitch(
                "s1",
                dpid=make_dpid(1),
            )

            area_base_dpid = 100
            ap_fallback_dpid = 1000

            switch_index = 2
            host_global_index = 1

            for area_index, area in enumerate(seed["topology"]["areas"], start=1):
                area_id = str(area.get("area_id", area_index))
                zone_id = str(area.get("zone_id", ""))
                area_name = str(area.get("area_name", area_id))

                area_switch_name = "s{}".format(switch_index)
                switch_index += 1

                area_dpid = make_dpid(area_base_dpid + area_index)

                node_map["area_switch_map"][area_id] = {
                    "switch_node": area_switch_name,
                    "area_id": area_id,
                    "zone_id": zone_id,
                    "area_name": area_name,
                    "dpid": area_dpid,
                }

                area_switch = self.addSwitch(
                    area_switch_name,
                    dpid=area_dpid,
                )

                uplink = area.get("uplink", {})
                uplink_bw = float(uplink.get("bw", 100))
                uplink_delay = str(uplink.get("delay", "2ms"))

                self.addLink(
                    core_switch,
                    area_switch,
                    cls=TCLink,
                    bw=uplink_bw,
                    delay=uplink_delay,
                )

                for ap_index, ap in enumerate(area.get("aps", []), start=1):
                    ap = dict(ap)
                    ap["area_id"] = area_id
                    ap["zone_id"] = zone_id
                    ap["area_name"] = area_name

                    device_id = str(ap.get("device_id", "AP-{}-{}".format(area_id, ap_index)))

                    ap_switch_name = "s{}".format(switch_index)
                    switch_index += 1

                    raw_dpid = ap.get(
                        "dpid",
                        ap_fallback_dpid + area_index * 100 + ap_index,
                    )
                    normalized_dpid = make_dpid(raw_dpid)

                    add_device_to_node_map(
                        node_map=node_map,
                        device_id=device_id,
                        switch_node=ap_switch_name,
                        dpid=normalized_dpid,
                        ap=ap,
                    )

                    ap_switch = self.addSwitch(
                        ap_switch_name,
                        dpid=normalized_dpid,
                    )

                    link = ap.get("link", {})
                    ap_bw = float(link.get("bw", 50))
                    ap_delay = str(link.get("delay", "3ms"))

                    self.addLink(
                        area_switch,
                        ap_switch,
                        cls=TCLink,
                        bw=ap_bw,
                        delay=ap_delay,
                    )

                    client_count = int(ap.get("clients", 1))

                    # 为了测试速度，每个 AP 最多模拟 2 个 host。
                    # clients 的真实数量仍然保存在 seed 和 label 里。
                    simulated_hosts = max(1, min(client_count, 2))

                    for client_idx in range(1, simulated_hosts + 1):
                        # 必须短，避免 h_AP_EXAM_302-eth0 超过 Linux ifname 限制。
                        host_name = "h{}".format(host_global_index)
                        host_global_index += 1

                        # 给 host 一个简单 IP，便于 Mininet 内部测试。
                        # 这个不是 management_ip。
                        # management_ip 是设备管理 IP，来自 topology_seed.json。
                        host_ip = "10.0.0.{}/24".format(host_global_index)

                        add_host_to_node_map(
                            node_map=node_map,
                            host_name=host_name,
                            parent_device_id=device_id,
                            host_ip=host_ip,
                        )

                        host = self.addHost(
                            host_name,
                            ip=host_ip,
                        )

                        self.addLink(
                            host,
                            ap_switch,
                            cls=TCLink,
                            bw=max(1.0, ap_bw / 2.0),
                            delay=ap_delay,
                        )

    return CampusSeedTopo


def start_background_traffic(net) -> None:
    """
    简单启动背景 ping。

    主指标 ap_load 不是靠真实流量算出来的，
    而是由本脚本模拟并推送到 Pushgateway。
    这里的 ping 只是为了让 Mininet 里有基础流量。
    """
    hosts = net.hosts

    if len(hosts) < 2:
        print("[traffic] less than 2 hosts, skip background traffic")
        return

    print("[traffic] starting simple background ping traffic")

    try:
        h1 = hosts[0]
        h2 = hosts[-1]

        h1.cmd(
            "ping -i 1 {} > /tmp/mininet_ping_{}_{}.log 2>&1 &".format(
                h2.IP(),
                h1.name,
                h2.name,
            )
        )

        print("[traffic] {} ping {}".format(h1.name, h2.name))

    except Exception as e:
        print("[traffic] failed to start background traffic: {}".format(e))


def start_mininet(
    seed: Dict[str, Any],
    seed_path: str,
    duration: int,
    interval: int,
    anomaly_device: Optional[str],
    anomaly_after: int,
    print_payload: bool,
    no_traffic: bool,
    enter_cli: bool,
    controller_ip: str,
    controller_port: int,
    node_map_output: str,
) -> None:
    (
        Mininet,
        Topo,
        RemoteController,
        OVSKernelSwitch,
        TCLink,
        setLogLevel,
        CLI,
    ) = import_mininet_modules()

    setLogLevel("info")

    print("[mininet] building topology from topology_seed.json")

    if not check_port_open(controller_ip, controller_port):
        print(
            "[warning] Ryu controller {}:{} is not reachable now.".format(
                controller_ip,
                controller_port,
            )
        )
        print("[warning] please make sure this is running:")
        print(
            "ryu-manager --ofp-tcp-listen-port {} --wsapi-port 8080 phase2/flow_ai.py".format(
                controller_port
            )
        )

    node_map = empty_node_map(seed_path=seed_path)
    node_map["controller"] = {
        "type": "RemoteController",
        "ip": controller_ip,
        "port": controller_port,
    }

    CampusSeedTopo = build_mininet_topology_class(seed, node_map)
    topo = CampusSeedTopo()

    print_node_map_summary(node_map)
    write_json(node_map_output, node_map)
    print("[mapping] written to {}".format(node_map_output))

    print("[mininet] controller: RemoteController {}:{}".format(controller_ip, controller_port))

    net = None

    try:
        net = Mininet(
            topo=topo,
            controller=None,
            switch=OVSKernelSwitch,
            link=TCLink,
            autoSetMacs=True,
            autoStaticArp=True,
            build=False,
        )

        net.addController(
            "c0",
            controller=RemoteController,
            ip=controller_ip,
            port=controller_port,
        )

        net.build()
        net.start()

        print("[mininet] network started")

        if not no_traffic:
            start_background_traffic(net)
        else:
            print("[mininet] --no-traffic enabled, skip background traffic")

        run_metric_loop(
            seed=seed,
            duration=duration,
            interval=interval,
            anomaly_device=anomaly_device,
            anomaly_after=anomaly_after,
            print_payload=print_payload,
        )

        if enter_cli:
            print("[mininet] entering CLI")
            CLI(net)

    finally:
        if net is not None:
            print("[mininet] stopping network")
            net.stop()


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate Mininet topology from topology_seed.json and emit AP load metrics."
    )

    parser.add_argument(
        "--seed",
        default=DEFAULT_SEED,
        help="Path to topology seed json. Default: phase2/topology/topology_seed.json",
    )

    parser.add_argument(
        "--mode",
        choices=["dry-run", "emit-only", "run"],
        default="dry-run",
        help=(
            "dry-run: validate seed only; "
            "emit-only: push metrics only; "
            "run: start Mininet and push metrics."
        ),
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Run duration in seconds. Use 0 for infinite loop.",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Metric emit interval in seconds.",
    )

    parser.add_argument(
        "--anomaly-device",
        default="",
        help="Device that will become abnormal. Use empty string to disable.",
    )

    parser.add_argument(
        "--anomaly-after",
        type=int,
        default=30,
        help="Seconds after start to trigger anomaly.",
    )

    parser.add_argument(
        "--cli",
        action="store_true",
        help="Enter Mininet CLI after metric loop finishes.",
    )

    parser.add_argument(
        "--no-traffic",
        action="store_true",
        help="Do not start iperf/ping background traffic in Mininet mode.",
    )

    parser.add_argument(
        "--print-payload",
        action="store_true",
        help="Print Prometheus text payload before pushing.",
    )

    parser.add_argument(
        "--controller-ip",
        default=DEFAULT_CONTROLLER_IP,
        help="Ryu controller IP. Default: 127.0.0.1",
    )

    parser.add_argument(
        "--controller-port",
        type=int,
        default=DEFAULT_CONTROLLER_PORT,
        help="Ryu OpenFlow listen port. Default: 6633",
    )

    parser.add_argument(
        "--node-map-output",
        default=DEFAULT_NODE_MAP_OUTPUT,
        help="Where to write Mininet node map json.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    seed_path = os.path.abspath(args.seed)

    seed = load_json(seed_path)
    print_seed_summary(seed_path, seed)

    anomaly_device = args.anomaly_device.strip() or None

    if args.mode == "dry-run":
        print("[dry-run] seed is valid.")
        print("[dry-run] pushgateway_url: {}".format(get_pushgateway_url(seed)))
        print("[dry-run] job: {}".format(get_pushgateway_job(seed)))

        node_map = empty_node_map(seed_path=seed_path)
        print("[dry-run] node map output: {}".format(args.node_map_output))
        return

    if args.mode == "emit-only":
        print("[emit-only] only pushing metrics, not starting Mininet.")
        print("[emit-only] business ID still uses topology_seed.json device_id.")

        run_metric_loop(
            seed=seed,
            duration=args.duration,
            interval=args.interval,
            anomaly_device=anomaly_device,
            anomaly_after=args.anomaly_after,
            print_payload=args.print_payload,
        )
        return

    if args.mode == "run":
        start_mininet(
            seed=seed,
            seed_path=seed_path,
            duration=args.duration,
            interval=args.interval,
            anomaly_device=anomaly_device,
            anomaly_after=args.anomaly_after,
            print_payload=args.print_payload,
            no_traffic=args.no_traffic,
            enter_cli=args.cli,
            controller_ip=args.controller_ip,
            controller_port=args.controller_port,
            node_map_output=args.node_map_output,
        )
        return


if __name__ == "__main__":
    main()