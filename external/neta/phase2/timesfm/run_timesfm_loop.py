# -*- coding: utf-8 -*-
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from timesfm_engine import TimesFMEngine
from device_map import build_watch_targets, get_device, generate_frontend_alert_text


def append_prediction_csv(prediction_file, result):
    path = Path(prediction_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    need_header = not path.exists()

    with path.open("a", newline="") as f:
        writer = csv.writer(f)

        if need_header:
            writer.writerow([
                "timestamp",
                "timestamp_iso",
                "device_id",
                "device_name",
                "zone_id",
                "area_id",
                "dpid",
                "port",
                "role",
                "metric",
                "external_metric",
                "future_step",
                "point",
                "q10",
                "q50",
                "q90",
                "history_last_value",
                "history_ci_low",
                "history_ci_high",
                "threshold",
                "trend",
                "risk",
                "risk_level",
                "exceed_confidence_interval",
                "exceed_threshold"
            ])

        ci_steps = set(result.get("exceed_confidence_interval_steps", []))
        threshold_steps = set(result.get("exceed_threshold_steps", []))

        for item in result["forecast"]:
            future_step = item["future_hour"]

            writer.writerow([
                result["timestamp"],
                result["timestamp_iso"],
                result["device_id"],
                result["device_name"],
                result["zone_id"],
                result["area_id"],
                result["dpid"],
                result["port"],
                result["role"],
                result["metric"],
                result["external_metric"],
                future_step,
                item["point"],
                item["q10"],
                item["q50"],
                item["q90"],
                result["history_last_value"],
                result["history_ci_low"],
                result["history_ci_high"],
                result["threshold"],
                result["trend"]["label"],
                result["risk"],
                result["risk_level"],
                future_step in ci_steps,
                future_step in threshold_steps
            ])


def append_alert_intent(alert_file, result):
    if not result["risk"]:
        return None

    path = Path(alert_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    q90_values = [x["q90"] for x in result["forecast"]]
    point_values = [x["point"] for x in result["forecast"]]

    peak_q90 = float(max(q90_values))
    peak_point = float(max(point_values))
    peak_step = int(q90_values.index(peak_q90) + 1)

    alert = {
        "timestamp": result["timestamp"],
        "timestamp_iso": result["timestamp_iso"],
        "source": "TimesFM",
        "type": "forecast_alert_intent",
        "intent": "send_warning_to_qwen3",
        "device_id": result["device_id"],
        "device_name": result["device_name"],
        "zone_id": result["zone_id"],
        "area_id": result["area_id"],
        "dpid": result["dpid"],
        "port": result["port"],
        "role": result["role"],
        "metric": result["metric"],
        "external_metric": result["external_metric"],
        "horizon": result["horizon_hours"],
        "future_peak_step": peak_step,
        "history_last_value": result["history_last_value"],
        "history_ci_low": result["history_ci_low"],
        "history_ci_high": result["history_ci_high"],
        "predicted_point_peak": peak_point,
        "predicted_q90_peak": peak_q90,
        "threshold": result["threshold"],
        "trend": result["trend"],
        "risk": result["risk"],
        "risk_level": result["risk_level"],
        "frontend_alert": generate_frontend_alert_text(
            result["device_id"],
            result["metric"],
            peak_step,
            result["risk_level"]
        ),
        "defense_status": "strategy_generating",
        "reason": "TimesFM 预测值超过历史置信区间或超过阈值，需要交给 Qwen3 生成主动防御策略"
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(alert, ensure_ascii=False) + "\n")

    return alert


def classify_risk(result):
    q90_peak = max([x["q90"] for x in result["forecast"]])
    threshold = result.get("threshold")

    if result.get("risk"):
        return "HIGH"

    if threshold is not None and q90_peak >= float(threshold) * 0.8:
        return "MEDIUM"

    if result["trend"]["label"] == "rising":
        return "MEDIUM"

    return "LOW"


def enrich_result_with_device(result, target):
    device = get_device(target["device_id"])

    result["device_id"] = target["device_id"]
    result["device_name"] = device.get("name", target["device_id"])
    result["zone_id"] = device.get("zone_id")
    result["area_id"] = device.get("area_id")
    result["external_metric"] = target["external_metric"]
    result["risk_level"] = classify_risk(result)

    return result


def main():
    parser = argparse.ArgumentParser(description="TimesFM 持续预测循环")

    parser.add_argument(
        "--model-id",
        default="/home/jowin/Desktop/neta/models/timesfm-2.5-200m-pytorch"
    )
    parser.add_argument(
        "--telemetry",
        default="/home/jowin/Desktop/neta/phase2/data/telemetry.csv"
    )
    parser.add_argument(
        "--prediction",
        default="/home/jowin/Desktop/neta/phase2/data/prediction.csv"
    )
    parser.add_argument(
        "--alert-file",
        default="/home/jowin/Desktop/neta/phase2/data/alert_intents.jsonl"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="每隔多少秒预测一次"
    )
    parser.add_argument(
        "--hour-seconds",
        type=int,
        default=5,
        help="实验压缩时间。5 表示每 5 秒作为一个预测时间步"
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=24
    )
    parser.add_argument(
        "--min-context",
        type=int,
        default=3
    )
    parser.add_argument(
        "--include-loss",
        action="store_true",
        help="是否同时预测 loss"
    )

    args = parser.parse_args()

    watch_targets = build_watch_targets(include_loss=args.include_loss)

    engine = TimesFMEngine(
        model_id=args.model_id,
        max_context=1024,
        max_horizon=max(24, args.horizon)
    )

    print("========== TimesFM 持续预测服务启动 ==========")
    print("启动时间:", datetime.now().isoformat(timespec="seconds"))
    print("模型路径:", args.model_id)
    print("遥测文件:", args.telemetry)
    print("预测结果:", args.prediction)
    print("预警文件:", args.alert_file)
    print("预测间隔:", args.interval, "秒")
    print("实验时间步 hour_seconds:", args.hour_seconds)
    print("监控对象:", json.dumps(watch_targets, ensure_ascii=False, indent=2))

    while True:
        print("\n========== 新一轮 TimesFM 预测 ==========")
        print("时间:", datetime.now().isoformat(timespec="seconds"))

        for target in watch_targets:
            try:
                result = engine.forecast_metric(
                    telemetry_file=args.telemetry,
                    dpid=target["dpid"],
                    port=target["port"],
                    metric=target["metric"],
                    horizon=args.horizon,
                    hour_seconds=args.hour_seconds,
                    min_context=args.min_context,
                    threshold=target["threshold"]
                )

                result = enrich_result_with_device(result, target)

                append_prediction_csv(args.prediction, result)
                alert = append_alert_intent(args.alert_file, result)

                q90_peak = max([x["q90"] for x in result["forecast"]])
                point_peak = max([x["point"] for x in result["forecast"]])

                print(
                    "[OK] device_id={} name={} dpid={} port={} metric={} risk={} "
                    "risk_level={} point_peak={:.8f} q90_peak={:.8f} ci_high={:.8f}".format(
                        result["device_id"],
                        result["device_name"],
                        result["dpid"],
                        result["port"],
                        result["external_metric"],
                        result["risk"],
                        result["risk_level"],
                        point_peak,
                        q90_peak,
                        result["history_ci_high"]
                    )
                )

                if alert:
                    print("[ALERT] 已生成预测告警:", json.dumps(alert, ensure_ascii=False))

            except Exception as e:
                print(
                    "[ERROR] device_id={} dpid={} port={} metric={} error={}".format(
                        target["device_id"],
                        target["dpid"],
                        target["port"],
                        target["metric"],
                        str(e)
                    )
                )

        time.sleep(args.interval)


if __name__ == "__main__":
    main()