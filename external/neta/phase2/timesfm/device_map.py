# -*- coding: utf-8 -*-

DEVICE_MAP = {
    "AP-EXAM-301": {
        "device_id": "AP-EXAM-301",
        "name": "301考场AP",
        "zone_id": "ZONE-TEACH",
        "area_id": "301",
        "layer": "access",
        "role": "teaching_ap",
        "dpid": 5,
        "port": 1,
        "management_ip": "10.0.1.101",
        "primary_suspect_ip": "192.168.1.10",
        "suspect_hosts": ["192.168.1.10", "192.168.1.14", "192.168.1.18"],
        "thresholds": {"load": 0.80, "loss": 0.05},
    },
    "AP-EXAM-302": {
        "device_id": "AP-EXAM-302",
        "name": "302考场AP",
        "zone_id": "ZONE-TEACH",
        "area_id": "302",
        "layer": "access",
        "role": "teaching_ap",
        "dpid": 6,
        "port": 1,
        "management_ip": "10.0.1.102",
        "primary_suspect_ip": "192.168.1.11",
        "suspect_hosts": ["192.168.1.11", "192.168.1.15", "192.168.1.19"],
        "thresholds": {"load": 0.80, "loss": 0.05},
    },
    "AP-EXAM-303": {
        "device_id": "AP-EXAM-303",
        "name": "303考场AP",
        "zone_id": "ZONE-TEACH",
        "area_id": "303",
        "layer": "access",
        "role": "teaching_ap",
        "dpid": 7,
        "port": 1,
        "management_ip": "10.0.1.103",
        "primary_suspect_ip": "192.168.1.12",
        "suspect_hosts": ["192.168.1.12", "192.168.1.16"],
        "thresholds": {"load": 0.80, "loss": 0.05},
    },
    "AP-LIB-A1": {
        "device_id": "AP-LIB-A1",
        "name": "图书馆A1 AP",
        "zone_id": "ZONE-DORM",
        "area_id": "LIB",
        "layer": "access",
        "role": "dorm_ap",
        "dpid": 9,
        "port": 1,
        "management_ip": "10.0.2.101",
        "primary_suspect_ip": "192.168.2.10",
        "suspect_hosts": ["192.168.2.10", "192.168.2.14", "192.168.2.18"],
        "thresholds": {"load": 0.80, "loss": 0.05},
    },
    "AP-DORM-A1": {
        "device_id": "AP-DORM-A1",
        "name": "宿舍A区A1 AP",
        "zone_id": "ZONE-DORM",
        "area_id": "DORM-A",
        "layer": "access",
        "role": "dorm_ap",
        "dpid": 10,
        "port": 1,
        "management_ip": "10.0.2.201",
        "primary_suspect_ip": "192.168.2.11",
        "suspect_hosts": ["192.168.2.11", "192.168.2.15", "192.168.2.19"],
        "thresholds": {"load": 0.80, "loss": 0.05},
    },
    "AP-DORM-A2": {
        "device_id": "AP-DORM-A2",
        "name": "宿舍A区A2 AP",
        "zone_id": "ZONE-DORM",
        "area_id": "DORM-A",
        "layer": "access",
        "role": "dorm_ap",
        "dpid": 11,
        "port": 1,
        "management_ip": "10.0.2.202",
        "primary_suspect_ip": "192.168.2.12",
        "suspect_hosts": ["192.168.2.12", "192.168.2.16"],
        "thresholds": {"load": 0.80, "loss": 0.05},
    },
    "SRV-EXAM": {
        "device_id": "SRV-EXAM",
        "name": "考试业务服务器",
        "zone_id": "ZONE-DC",
        "area_id": "DC",
        "layer": "server",
        "role": "server",
        "host": "web",
        "ip": "192.168.3.100",
    },
    "SRV-AUTH": {
        "device_id": "SRV-AUTH",
        "name": "认证服务器",
        "zone_id": "ZONE-DC",
        "area_id": "DC",
        "layer": "server",
        "role": "server",
        "host": "dns",
        "ip": "192.168.3.101",
    },
    "SRV-GATEWAY": {
        "device_id": "SRV-GATEWAY",
        "name": "校园网网关",
        "zone_id": "ZONE-DC",
        "area_id": "DC",
        "layer": "server",
        "role": "gateway",
        "host": "gw",
        "ip": "192.168.3.1",
    },
    "OF-CORE-01": {
        "device_id": "OF-CORE-01",
        "name": "核心OpenFlow交换机",
        "zone_id": "ZONE-CORE",
        "area_id": "CORE",
        "layer": "core",
        "role": "core_switch",
        "dpid": 1,
    },
    "RYU-CTRL-01": {
        "device_id": "RYU-CTRL-01",
        "name": "Ryu SDN控制器",
        "zone_id": "ZONE-CORE",
        "area_id": "CORE",
        "layer": "controller",
        "role": "sdn_controller",
        "management_ip": "127.0.0.1",
    },
}

AP_DEVICE_IDS = [
    "AP-EXAM-301",
    "AP-EXAM-302",
    "AP-EXAM-303",
    "AP-LIB-A1",
    "AP-DORM-A1",
    "AP-DORM-A2",
]


def get_device(device_id):
    if device_id not in DEVICE_MAP:
        raise ValueError("未知 device_id: {}".format(device_id))
    return DEVICE_MAP[device_id]


def is_ap_device(device_id):
    return device_id in AP_DEVICE_IDS


def metric_to_internal(metric):
    if metric in ("ap_load", "load", "device_load"):
        return "load"
    if metric in ("ap_loss", "loss", "packet_loss", "packet_loss_rate"):
        return "loss"
    raise ValueError("不支持的 metric: {}".format(metric))


def internal_to_external_metric(metric):
    if metric == "load":
        return "ap_load"
    if metric == "loss":
        return "ap_loss"
    return metric


def get_threshold(device_id, internal_metric):
    device = get_device(device_id)
    return float(device.get("thresholds", {}).get(internal_metric, 0.8))


def device_to_telemetry_query(device_id, metric):
    device = get_device(device_id)
    internal_metric = metric_to_internal(metric)

    if "dpid" not in device or "port" not in device:
        raise ValueError("device_id={} 不是可预测的 AP/交换机设备".format(device_id))

    return {
        "device_id": device_id,
        "dpid": int(device["dpid"]),
        "port": int(device["port"]),
        "metric": internal_metric,
        "external_metric": internal_to_external_metric(internal_metric),
        "threshold": get_threshold(device_id, internal_metric),
        "role": device.get("role"),
        "zone_id": device.get("zone_id"),
        "area_id": device.get("area_id"),
        "name": device.get("name", device_id),
        "management_ip": device.get("management_ip"),
        "primary_suspect_ip": device.get("primary_suspect_ip"),
        "suspect_hosts": device.get("suspect_hosts", []),
    }


def build_watch_targets(include_loss=True):
    targets = []

    for device_id in AP_DEVICE_IDS:
        device = get_device(device_id)

        targets.append({
            "device_id": device_id,
            "dpid": int(device["dpid"]),
            "port": int(device["port"]),
            "metric": "load",
            "external_metric": "ap_load",
            "threshold": get_threshold(device_id, "load"),
        })

        if include_loss:
            targets.append({
                "device_id": device_id,
                "dpid": int(device["dpid"]),
                "port": int(device["port"]),
                "metric": "loss",
                "external_metric": "ap_loss",
                "threshold": get_threshold(device_id, "loss"),
            })

    return targets


def generate_frontend_alert_text(device_id, metric, peak_step, risk):
    device = get_device(device_id)
    name = device.get("name", device_id)

    if metric in ("load", "ap_load"):
        event_text = "预计过载"
    elif metric in ("loss", "ap_loss"):
        event_text = "预计丢包异常"
    else:
        event_text = "预计异常"

    if risk == "HIGH":
        return "未来{}个时间步：{}({}){}，建议触发主动防御".format(
            peak_step,
            device_id,
            name,
            event_text
        )

    return "未来{}个时间步：{}({})风险较低".format(
        peak_step,
        device_id,
        name
    )
