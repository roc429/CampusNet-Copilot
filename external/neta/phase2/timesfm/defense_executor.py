import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime

import requests

CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from device_map import get_device


DEFAULT_ALERT_FILE = "/home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl"
DEFAULT_STATUS_FILE = "/home/jowin/Desktop/neta/phase2/data/defense_status.jsonl"
DEFAULT_RYU_API = "http://127.0.0.1:8080/policy/apply"


def build_alert_id(alert):
    return "{}-{}-{}-{}-{}".format(
        alert.get("timestamp"),
        alert.get("device_id"),
        alert.get("metric"),
        alert.get("future_peak_step"),
        alert.get("predicted_q90_peak")
    )


def load_new_alerts(alert_file, consumed_ids):
    path = Path(alert_file).expanduser()
    if not path.exists():
        return []

    alerts = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                alert = json.loads(line)
            except Exception:
                continue

            alert_id = build_alert_id(alert)

            if alert_id not in consumed_ids:
                alerts.append(alert)

    return alerts


def generate_policy(alert):
    """
    当前阶段规则生成策略。
    后面接 Qwen3 时，把这里替换为 Qwen3 生成策略即可。

    输入 alert 使用统一 device_id。
    输出 policy 使用 Ryu /policy/apply 需要的 dpid、match。
    """
    device_id = alert.get("device_id")

    if not device_id:
        return {
            "action": "do_nothing",
            "reason": "告警中缺少 device_id，不执行主动防御"
        }

    device = get_device(device_id)

    if "dpid" not in device:
        return {
            "action": "do_nothing",
            "reason": "device_id={} 不是可下发流表的 AP 设备".format(device_id)
        }

    target_ip = device.get("primary_suspect_ip")
    dpid = int(device["dpid"])

    if not target_ip:
        return {
            "action": "do_nothing",
            "reason": "device_id={} 没有配置 primary_suspect_ip".format(device_id)
        }

    metric = alert.get("metric")

    if metric == "loss":
        reason = "TimesFM 预测 {} 丢包率异常，临时阻断疑似异常主机 {}".format(
            device_id,
            target_ip
        )
    else:
        reason = "TimesFM 预测 {} 负载过高，临时阻断疑似异常主机 {}".format(
            device_id,
            target_ip
        )

    return {
        "action": "drop_host",
        "reason": reason,
        "device_id": device_id,
        "dpid": dpid,
        "priority": 220,
        "match": {
            "eth_type": 2048,
            "ipv4_src": target_ip
        },
        "duration": 60
    }


def validate_policy(policy):
    allowed_actions = {
        "do_nothing",
        "drop_host",
        "protect_server",
        "rate_limit_host"
    }

    if policy.get("action") not in allowed_actions:
        return False, "action_not_allowed"

    if policy.get("action") == "do_nothing":
        return True, "no_action"

    if "dpid" not in policy:
        return False, "missing_dpid"

    duration = int(policy.get("duration", 0))
    if duration <= 0 or duration > 300:
        return False, "invalid_duration"

    match = policy.get("match", {})
    src = match.get("ipv4_src")
    dst = match.get("ipv4_dst")

    protected_ips = {
        "192.168.3.1",
        "192.168.3.100",
        "192.168.3.101"
    }

    if src in protected_ips:
        return False, "forbidden_src_ip"

    if policy.get("action") == "drop_host" and dst in protected_ips:
        return False, "forbidden_drop_server"

    return True, "validated"


def apply_policy(policy, ryu_api):
    if policy.get("action") == "do_nothing":
        return {
            "ok": True,
            "message": "do_nothing"
        }

    r = requests.post(
        ryu_api,
        json=policy,
        timeout=5
    )

    try:
        return r.json()
    except Exception:
        return {
            "ok": False,
            "status_code": r.status_code,
            "text": r.text
        }


def append_status(status_file, record):
    path = Path(status_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def make_status(alert_id, stage, status_cn, **kwargs):
    record = {
        "timestamp": time.time(),
        "timestamp_iso": datetime.now().isoformat(timespec="seconds"),
        "alert_id": alert_id,
        "stage": stage,
        "status_cn": status_cn
    }
    record.update(kwargs)
    return record


def main():
    parser = argparse.ArgumentParser(description="TimesFM 告警主动防御执行器")

    parser.add_argument("--alert-file", default=DEFAULT_ALERT_FILE)
    parser.add_argument("--status-file", default=DEFAULT_STATUS_FILE)
    parser.add_argument("--ryu-api", default=DEFAULT_RYU_API)
    parser.add_argument("--interval", type=int, default=5)

    args = parser.parse_args()

    consumed_ids = set()

    print("========== 主动防御执行器启动 ==========")
    print("告警文件:", args.alert_file)
    print("状态文件:", args.status_file)
    print("Ryu API:", args.ryu_api)

    while True:
        alerts = load_new_alerts(args.alert_file, consumed_ids)

        for alert in alerts:
            alert_id = build_alert_id(alert)
            consumed_ids.add(alert_id)

            device_id = alert.get("device_id")

            print("\n[ALERT] 发现 TimesFM 预测告警")
            print(json.dumps(alert, ensure_ascii=False, indent=2))

            append_status(
                args.status_file,
                make_status(
                    alert_id,
                    "strategy_generating",
                    "策略生成中",
                    device_id=device_id,
                    alert=alert
                )
            )

            policy = generate_policy(alert)

            append_status(
                args.status_file,
                make_status(
                    alert_id,
                    "strategy_generated",
                    "策略已生成",
                    device_id=device_id,
                    policy=policy
                )
            )

            ok, reason = validate_policy(policy)

            append_status(
                args.status_file,
                make_status(
                    alert_id,
                    "semantic_guard_checked",
                    "语义审计完成",
                    device_id=device_id,
                    ok=ok,
                    reason=reason
                )
            )

            if not ok:
                print("[BLOCKED] 策略未通过语义校验:", reason)
                continue

            append_status(
                args.status_file,
                make_status(
                    alert_id,
                    "sandbox_verifying",
                    "沙盒验证中",
                    device_id=device_id,
                    policy=policy
                )
            )

            # 当前阶段先使用静态沙盒结果。
            # 下一步替换成真实 Mininet 外循环验证。
            sandbox_result = {
                "ok": True,
                "risk": "low",
                "message": "当前阶段为静态沙盒校验，已通过策略白名单和保护对象检查"
            }

            append_status(
                args.status_file,
                make_status(
                    alert_id,
                    "sandbox_verified",
                    "验证通过",
                    device_id=device_id,
                    sandbox_result=sandbox_result
                )
            )

            result = apply_policy(policy, args.ryu_api)

            append_status(
                args.status_file,
                make_status(
                    alert_id,
                    "policy_applied",
                    "已下发",
                    device_id=device_id,
                    policy=policy,
                    ryu_result=result
                )
            )

            print("[APPLIED] 主动防御策略已处理")
            print(json.dumps(result, ensure_ascii=False, indent=2))

        time.sleep(args.interval)


if __name__ == "__main__":
    main()