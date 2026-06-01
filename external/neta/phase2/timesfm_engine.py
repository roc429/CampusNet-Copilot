# -*- coding: utf-8 -*-
import argparse
import csv
import json
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

DEFAULT_TELEMETRY = os.path.join(DATA_DIR, "telemetry.csv")
DEFAULT_PREDICTION = os.path.join(DATA_DIR, "prediction.csv")
DEFAULT_ALERT = os.path.join(DATA_DIR, "alert_intents.jsonl")


class TimesFMEngine:
    def __init__(self, model_id="google/timesfm-2.5-200m-pytorch"):
        self.model_id = model_id
        self.model = None

    def load_model(self):
        if self.model is not None:
            return

        import torch
        import timesfm

        torch.set_float32_matmul_precision("high")

        self.model = timesfm.TimesFm(
            hparams=timesfm.TimesFmHparams(
                backend="torch",
                per_core_batch_size=32,
                horizon_len=24,
                input_patch_len=32,
                output_patch_len=128,
                num_layers=50,
                model_dims=1280,
                use_positional_embedding=False,
            ),
            checkpoint=timesfm.TimesFmCheckpoint(
                huggingface_repo_id=self.model_id
            ),
        )

    def load_series(self, telemetry_file, dpid, port, metric, hour_seconds):
        if not os.path.exists(telemetry_file):
            raise FileNotFoundError("找不到遥测文件: {}".format(telemetry_file))

        df = pd.read_csv(telemetry_file)

        need_cols = {"timestamp", "dpid", "port", "role", metric}
        missing = need_cols - set(df.columns)
        if missing:
            raise ValueError("telemetry.csv 缺少字段: {}".format(missing))

        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
        df["dpid"] = pd.to_numeric(df["dpid"], errors="coerce")
        df["port"] = pd.to_numeric(df["port"], errors="coerce")
        df[metric] = pd.to_numeric(df[metric], errors="coerce")

        df = df.dropna(subset=["timestamp", "dpid", "port", metric])

        df = df[
            (df["dpid"].astype(int) == int(dpid)) &
            (df["port"].astype(int) == int(port))
        ].copy()

        if df.empty:
            raise ValueError("没有找到 dpid={}, port={} 的数据".format(dpid, port))

        role = str(df["role"].iloc[-1])

        df["bucket"] = (
            df["timestamp"] // int(hour_seconds)
        ).astype(int) * int(hour_seconds)

        series_df = (
            df.groupby("bucket", as_index=False)[metric]
            .mean()
            .sort_values("bucket")
        )

        values = series_df[metric].astype(float).to_numpy()

        values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)

        if metric in ("load", "loss"):
            values = np.clip(values, 0.0, 1.0)

        return {
            "role": role,
            "values": values.astype(np.float32)
        }

    def extract_quantiles(self, point, quantile):
        q = np.asarray(quantile).astype(float)

        if q.ndim == 1:
            q = q.reshape(len(point), -1)

        if q.shape[0] != len(point) and q.shape[-1] == len(point):
            q = q.T

        if q.shape[0] != len(point):
            q = q[:len(point)]

        cols = q.shape[1]

        if cols >= 10:
            return q[:, 1], q[:, 5], q[:, 9]

        if cols >= 9:
            return q[:, 0], q[:, 4], q[:, 8]

        if cols >= 3:
            return q[:, 0], q[:, cols // 2], q[:, -1]

        return point.copy(), point.copy(), point.copy()

    def forecast(self, telemetry_file, dpid, port, metric,
                 horizon, hour_seconds, min_context, threshold):
        self.load_model()

        loaded = self.load_series(
            telemetry_file=telemetry_file,
            dpid=dpid,
            port=port,
            metric=metric,
            hour_seconds=hour_seconds
        )

        values = loaded["values"]

        if len(values) < min_context:
            raise ValueError(
                "上下文数据不足，当前 {} 个点，至少需要 {} 个点。"
                "可以多跑一会儿流量，或者降低 --min-context。".format(
                    len(values), min_context
                )
            )

        context = values[-1024:]

        point, quantile = self.model.forecast(
            [context],
            freq=[0]
        )

        point = np.asarray(point)[0].astype(float)
        quantile = np.asarray(quantile)[0].astype(float)

        q10, q50, q90 = self.extract_quantiles(point, quantile)

        history = values[-min(len(values), 128):]
        ci_low = float(np.quantile(history, 0.025))
        ci_high = float(np.quantile(history, 0.975))

        exceed_ci_steps = []
        exceed_threshold_steps = []

        for i in range(horizon):
            if point[i] > ci_high or q90[i] > ci_high:
                exceed_ci_steps.append(i + 1)

            if threshold is not None and q90[i] > threshold:
                exceed_threshold_steps.append(i + 1)

        risk = bool(exceed_ci_steps or exceed_threshold_steps)

        result = {
            "timestamp": time.time(),
            "timestamp_iso": datetime.now().isoformat(timespec="seconds"),
            "source": "TimesFM",
            "task": "zero_shot_forecast",
            "model": self.model_id,
            "dpid": int(dpid),
            "port": int(port),
            "role": loaded["role"],
            "metric": metric,
            "horizon_hours": int(horizon),
            "hour_seconds": int(hour_seconds),
            "context_points": int(len(context)),
            "history_last_value": float(values[-1]),
            "history_ci_low": ci_low,
            "history_ci_high": ci_high,
            "threshold": threshold,
            "risk": risk,
            "exceed_confidence_interval_steps": exceed_ci_steps,
            "exceed_threshold_steps": exceed_threshold_steps,
            "forecast": []
        }

        for i in range(horizon):
            result["forecast"].append({
                "future_hour": i + 1,
                "point": float(point[i]),
                "q10": float(q10[i]),
                "q50": float(q50[i]),
                "q90": float(q90[i])
            })

        return result


def append_prediction_csv(path, result):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    need_header = not os.path.exists(path)

    with open(path, "a", newline="") as f:
        writer = csv.writer(f)

        if need_header:
            writer.writerow([
                "timestamp",
                "timestamp_iso",
                "model",
                "dpid",
                "port",
                "role",
                "metric",
                "future_hour",
                "point",
                "q10",
                "q50",
                "q90",
                "history_last_value",
                "history_ci_low",
                "history_ci_high",
                "threshold",
                "risk"
            ])

        for item in result["forecast"]:
            writer.writerow([
                result["timestamp"],
                result["timestamp_iso"],
                result["model"],
                result["dpid"],
                result["port"],
                result["role"],
                result["metric"],
                item["future_hour"],
                item["point"],
                item["q10"],
                item["q50"],
                item["q90"],
                result["history_last_value"],
                result["history_ci_low"],
                result["history_ci_high"],
                result["threshold"],
                result["risk"]
            ])


def append_alert(path, result):
    if not result["risk"]:
        return None

    os.makedirs(os.path.dirname(path), exist_ok=True)

    q90_values = [x["q90"] for x in result["forecast"]]
    peak_q90 = max(q90_values)
    peak_hour = q90_values.index(peak_q90) + 1

    alert = {
        "timestamp": result["timestamp"],
        "timestamp_iso": result["timestamp_iso"],
        "source": "TimesFM",
        "type": "forecast_alert_intent",
        "intent": "send_warning_to_qwen3",
        "dpid": result["dpid"],
        "port": result["port"],
        "role": result["role"],
        "metric": result["metric"],
        "horizon_hours": result["horizon_hours"],
        "future_peak_hour": peak_hour,
        "history_last_value": result["history_last_value"],
        "history_ci_low": result["history_ci_low"],
        "history_ci_high": result["history_ci_high"],
        "predicted_q90_peak": float(peak_q90),
        "threshold": result["threshold"],
        "reason": "TimesFM预测值超过历史置信区间或指定阈值，需要交给Qwen3生成主动防御策略"
    }

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(alert, ensure_ascii=False) + "\n")

    return alert


def print_result(result, alert):
    print("\n========== TimesFM 预测结果 ==========")
    print("模型:", result["model"])
    print("对象: dpid={}, port={}, role={}".format(
        result["dpid"], result["port"], result["role"]
    ))
    print("指标:", result["metric"])
    print("预测范围: 未来 1-{} 小时".format(result["horizon_hours"]))
    print("上下文点数:", result["context_points"])
    print("历史当前值:", result["history_last_value"])
    print("历史置信区间: [{}, {}]".format(
        result["history_ci_low"],
        result["history_ci_high"]
    ))
    print("是否风险:", result["risk"])

    for item in result["forecast"]:
        print(
            "第{:02d}小时 | point={:.8f} | q10={:.8f} | q50={:.8f} | q90={:.8f}".format(
                item["future_hour"],
                item["point"],
                item["q10"],
                item["q50"],
                item["q90"]
            )
        )

    if alert:
        print("\n已生成预警意图:")
        print(json.dumps(alert, ensure_ascii=False, indent=2))
    else:
        print("\n未生成预警意图。")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--telemetry", default=DEFAULT_TELEMETRY)
    parser.add_argument("--prediction", default=DEFAULT_PREDICTION)
    parser.add_argument("--alert-file", default=DEFAULT_ALERT)

    parser.add_argument("--dpid", type=int, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--metric", choices=["load", "loss"], required=True)

    parser.add_argument("--horizon", type=int, default=24)
    parser.add_argument("--hour-seconds", type=int, default=5)
    parser.add_argument("--min-context", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=None)

    args = parser.parse_args()

    engine = TimesFMEngine()

    result = engine.forecast(
        telemetry_file=args.telemetry,
        dpid=args.dpid,
        port=args.port,
        metric=args.metric,
        horizon=args.horizon,
        hour_seconds=args.hour_seconds,
        min_context=args.min_context,
        threshold=args.threshold
    )

    append_prediction_csv(args.prediction, result)
    alert = append_alert(args.alert_file, result)

    print_result(result, alert)


if __name__ == "__main__":
    main()