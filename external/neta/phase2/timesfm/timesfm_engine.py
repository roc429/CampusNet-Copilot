# -*- coding: utf-8 -*-
import argparse
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
PHASE2_DIR = BASE_DIR.parent
PROJECT_DIR = PHASE2_DIR.parent

DEFAULT_TELEMETRY_FILE = PHASE2_DIR / "data" / "telemetry.csv"
DEFAULT_PREDICTION_FILE = PHASE2_DIR / "data" / "prediction.csv"
DEFAULT_ALERT_FILE = PHASE2_DIR / "data" / "alert_intents.jsonl"
DEFAULT_LOCAL_MODEL_DIR = PROJECT_DIR / "models" / "timesfm-2.5-200m-pytorch"


class TimesFMEngine:
    def __init__(self, model_id=None, max_context=1024, max_horizon=24):
        if model_id is None:
            if DEFAULT_LOCAL_MODEL_DIR.exists():
                model_id = str(DEFAULT_LOCAL_MODEL_DIR)
            else:
                model_id = "google/timesfm-2.5-200m-pytorch"

        self.model_id = str(model_id)
        self.max_context = int(max_context)
        self.max_horizon = int(max_horizon)
        self.model = None

    def load_model(self):
        if self.model is not None:
            return

        try:
            import torch
            import timesfm
        except ImportError as e:
            raise RuntimeError(
                "TimesFM 或 PyTorch 未正确安装。请先激活虚拟环境："
                "source ~/Desktop/neta/phase2/timesfm/.venv/bin/activate。"
                "原始错误: {}".format(e)
            )

        torch.set_float32_matmul_precision("high")

        model_path = Path(self.model_id).expanduser()

        if model_path.exists() and model_path.is_dir():
            safetensors_path = model_path / "model.safetensors"
            ckpt_path = model_path / "torch_model.ckpt"

            if safetensors_path.exists():
                print("使用本地 TimesFM safetensors 模型: {}".format(model_path))
            elif ckpt_path.exists():
                print("使用本地 TimesFM ckpt 模型: {}".format(model_path))
            else:
                raise FileNotFoundError(
                    "本地模型目录存在，但未找到 model.safetensors 或 torch_model.ckpt: {}".format(
                        model_path
                    )
                )

            # 新版 TimesFM 2.5 会自动读取本地目录中的 model.safetensors
            self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                str(model_path)
            )
        else:
            print("使用 Hugging Face 模型: {}".format(self.model_id))
            self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
                self.model_id
            )

        self.model.compile(
            timesfm.ForecastConfig(
                max_context=self.max_context,
                max_horizon=self.max_horizon,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                force_flip_invariance=True,
                infer_is_positive=True,
                fix_quantile_crossing=True,
            )
        )

    def load_metric_series(self, telemetry_file, dpid, port, metric, hour_seconds=3600):
        telemetry_file = Path(telemetry_file).expanduser()

        if not telemetry_file.exists():
            raise FileNotFoundError("找不到遥测文件: {}".format(telemetry_file))

        df = pd.read_csv(telemetry_file)

        required_columns = {"timestamp", "dpid", "port", "role", metric}
        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError("telemetry.csv 缺少字段: {}".format(sorted(missing)))

        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
        df["dpid"] = pd.to_numeric(df["dpid"], errors="coerce")
        df["port"] = pd.to_numeric(df["port"], errors="coerce")
        df[metric] = pd.to_numeric(df[metric], errors="coerce")

        df = df.dropna(subset=["timestamp", "dpid", "port", metric])

        selected = df[
            (df["dpid"].astype(int) == int(dpid))
            & (df["port"].astype(int) == int(port))
        ].copy()

        if selected.empty:
            available = (
                df[["dpid", "port", "role"]]
                .drop_duplicates()
                .sort_values(["dpid", "port"])
                .head(80)
            )
            raise ValueError(
                "没有找到 dpid={}, port={} 的数据。可用端口示例:\n{}".format(
                    dpid,
                    port,
                    available.to_string(index=False)
                )
            )

        selected = selected.sort_values("timestamp")
        role = str(selected["role"].dropna().iloc[-1])

        selected["bucket"] = (
            selected["timestamp"] // int(hour_seconds)
        ).astype(int) * int(hour_seconds)

        series_df = (
            selected.groupby("bucket", as_index=False)[metric]
            .mean()
            .sort_values("bucket")
        )

        if series_df.empty:
            raise ValueError("筛选后没有可用序列数据")

        min_bucket = int(series_df["bucket"].min())
        max_bucket = int(series_df["bucket"].max())

        full_buckets = np.arange(
            min_bucket,
            max_bucket + int(hour_seconds),
            int(hour_seconds)
        )

        full_df = pd.DataFrame({"bucket": full_buckets})
        full_df = full_df.merge(series_df, on="bucket", how="left")

        full_df[metric] = (
            full_df[metric]
            .interpolate()
            .ffill()
            .bfill()
        )

        values = full_df[metric].astype(float).to_numpy()

        if metric in ("load", "loss"):
            values = np.clip(values, 0.0, 1.0)

        return {
            "dpid": int(dpid),
            "port": int(port),
            "role": role,
            "metric": metric,
            "hour_seconds": int(hour_seconds),
            "buckets": full_df["bucket"].astype(float).to_numpy(),
            "values": values.astype(np.float32)
        }

    def forecast_metric(
        self,
        telemetry_file,
        dpid,
        port,
        metric,
        horizon=24,
        hour_seconds=3600,
        min_context=8,
        threshold=None
    ):
        horizon = int(horizon)

        if horizon > self.max_horizon:
            raise ValueError(
                "horizon={} 超过 max_horizon={}。".format(
                    horizon,
                    self.max_horizon
                )
            )

        self.load_model()

        loaded = self.load_metric_series(
            telemetry_file=telemetry_file,
            dpid=dpid,
            port=port,
            metric=metric,
            hour_seconds=hour_seconds
        )

        values = loaded["values"]

        if len(values) < int(min_context):
            raise ValueError(
                "TimesFM 上下文数据不足。当前只有 {} 个时间点，至少需要 {} 个。"
                "测试时可以多运行一会儿 Ryu 遥测，或者把 --hour-seconds 设置小一些。".format(
                    len(values),
                    min_context
                )
            )

        context = values[-self.max_context:]

        point_forecast, quantile_forecast = self._run_forecast(
            context=context,
            horizon=horizon
        )

        point = np.asarray(point_forecast)[0].astype(float)
        quantile = np.asarray(quantile_forecast)[0].astype(float)

        q10, q50, q90 = self.extract_quantiles(point, quantile)

        history = values[-min(len(values), self.max_context):]
        ci_low, ci_high = self.history_confidence_interval(history)

        exceed_steps = []
        threshold_steps = []

        for i in range(horizon):
            point_exceed = point[i] > ci_high or point[i] < ci_low
            q90_exceed = q90[i] > ci_high

            if point_exceed or q90_exceed:
                exceed_steps.append(i + 1)

            if threshold is not None and q90[i] > float(threshold):
                threshold_steps.append(i + 1)

        trend = self.estimate_trend(point, history)
        risk = bool(exceed_steps or threshold_steps)

        result = {
            "timestamp": time.time(),
            "timestamp_iso": datetime.now().isoformat(timespec="seconds"),
            "model": self.model_id,
            "task": "timesfm_zero_shot_forecast",
            "dpid": loaded["dpid"],
            "port": loaded["port"],
            "role": loaded["role"],
            "metric": metric,
            "horizon_hours": horizon,
            "hour_seconds": int(hour_seconds),
            "context_points": int(len(context)),
            "history_last_value": float(values[-1]),
            "history_ci_low": float(ci_low),
            "history_ci_high": float(ci_high),
            "threshold": None if threshold is None else float(threshold),
            "trend": trend,
            "risk": risk,
            "exceed_confidence_interval_steps": exceed_steps,
            "exceed_threshold_steps": threshold_steps,
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

    def _run_forecast(self, context, horizon):
        context = np.asarray(context, dtype=np.float32)

        try:
            return self.model.forecast(
                horizon=int(horizon),
                inputs=[context]
            )
        except TypeError:
            pass

        try:
            return self.model.forecast(
                inputs=[context],
                horizon=int(horizon)
            )
        except TypeError:
            pass

        try:
            return self.model.forecast(
                [context],
                int(horizon)
            )
        except TypeError as e:
            raise RuntimeError(
                "当前 TimesFM forecast API 与脚本不匹配。原始错误: {}".format(e)
            )

    def extract_quantiles(self, point, quantile):
        q = np.asarray(quantile).astype(float)

        if q.ndim == 1:
            q = q.reshape(len(point), -1)

        if q.shape[0] != len(point) and q.shape[-1] == len(point):
            q = q.T

        if q.shape[0] != len(point):
            q = q[:len(point)]

        columns = q.shape[1]

        # TimesFM 2.5 常见输出列：mean, q10, q20, ..., q90
        if columns >= 10:
            q10 = q[:, 1]
            q50 = q[:, 5]
            q90 = q[:, 9]
            return q10, q50, q90

        if columns >= 9:
            q10 = q[:, 0]
            q50 = q[:, 4]
            q90 = q[:, 8]
            return q10, q50, q90

        if columns >= 3:
            q10 = q[:, 0]
            q50 = q[:, columns // 2]
            q90 = q[:, -1]
            return q10, q50, q90

        return point.copy(), point.copy(), point.copy()

    def history_confidence_interval(self, history):
        history = np.asarray(history).astype(float)

        if len(history) < 4:
            value = float(history[-1])
            return value, value

        ci_low = float(np.quantile(history, 0.025))
        ci_high = float(np.quantile(history, 0.975))

        return ci_low, ci_high

    def estimate_trend(self, point, history):
        point = np.asarray(point).astype(float)

        if len(point) < 2:
            return {
                "label": "stable",
                "slope": 0.0,
                "normalized_slope": 0.0
            }

        x = np.arange(len(point))
        slope = float(np.polyfit(x, point, 1)[0])

        base = float(np.mean(np.abs(history))) + 1e-9
        normalized_slope = float(slope / base)

        if normalized_slope > 0.02:
            label = "rising"
        elif normalized_slope < -0.02:
            label = "falling"
        else:
            label = "stable"

        return {
            "label": label,
            "slope": slope,
            "normalized_slope": normalized_slope
        }


def append_prediction_csv(prediction_file, result):
    prediction_file = Path(prediction_file).expanduser()
    prediction_file.parent.mkdir(parents=True, exist_ok=True)

    need_header = not prediction_file.exists()

    with prediction_file.open("a", newline="") as f:
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
                "trend",
                "risk",
                "exceed_confidence_interval",
                "exceed_threshold"
            ])

        ci_steps = set(result["exceed_confidence_interval_steps"])
        threshold_steps = set(result["exceed_threshold_steps"])

        for item in result["forecast"]:
            future_hour = item["future_hour"]

            writer.writerow([
                result["timestamp"],
                result["timestamp_iso"],
                result["model"],
                result["dpid"],
                result["port"],
                result["role"],
                result["metric"],
                future_hour,
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
                future_hour in ci_steps,
                future_hour in threshold_steps
            ])


def append_alert_intent(alert_file, result):
    if not result["risk"]:
        return None

    alert_file = Path(alert_file).expanduser()
    alert_file.parent.mkdir(parents=True, exist_ok=True)

    q90_values = [x["q90"] for x in result["forecast"]]
    point_values = [x["point"] for x in result["forecast"]]

    peak_q90 = float(max(q90_values))
    peak_point = float(max(point_values))
    peak_hour = int(q90_values.index(peak_q90) + 1)

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
        "predicted_point_peak": peak_point,
        "predicted_q90_peak": peak_q90,
        "threshold": result["threshold"],
        "trend": result["trend"],
        "reason": "TimesFM 预测值超过历史置信区间或超过阈值，需要交给 Qwen3 生成主动防御策略"
    }

    with alert_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(alert, ensure_ascii=False) + "\n")

    return alert


def print_summary(result, alert):
    print("\n========== TimesFM 预测结果 ==========")
    print("模型: {}".format(result["model"]))
    print("对象: dpid={}, port={}, role={}".format(
        result["dpid"],
        result["port"],
        result["role"]
    ))
    print("指标: {}".format(result["metric"]))
    print("预测范围: 未来 1-{} 小时".format(result["horizon_hours"]))
    print("上下文点数: {}".format(result["context_points"]))
    print("历史当前值: {:.8f}".format(result["history_last_value"]))
    print("历史置信区间: [{:.8f}, {:.8f}]".format(
        result["history_ci_low"],
        result["history_ci_high"]
    ))
    print("阈值: {}".format(result["threshold"]))
    print("趋势: {}".format(result["trend"]["label"]))
    print("是否风险: {}".format(result["risk"]))

    print("\n未来预测:")
    for item in result["forecast"]:
        print(
            "第 {:02d} 小时 | point={:.8f} | q10={:.8f} | q50={:.8f} | q90={:.8f}".format(
                item["future_hour"],
                item["point"],
                item["q10"],
                item["q50"],
                item["q90"]
            )
        )

    if alert is not None:
        print("\n已生成预警意图:")
        print(json.dumps(alert, ensure_ascii=False, indent=2))
    else:
        print("\n未生成预警意图。预测结果未超过置信区间或阈值。")


def main():
    parser = argparse.ArgumentParser(
        description="TimesFM 零样本预测引擎，用于预测校园网 AP 负载和丢包率"
    )

    parser.add_argument(
        "--telemetry",
        default=str(DEFAULT_TELEMETRY_FILE),
        help="Ryu 遥测 CSV 文件路径"
    )
    parser.add_argument(
        "--prediction",
        default=str(DEFAULT_PREDICTION_FILE),
        help="预测结果 CSV 输出路径"
    )
    parser.add_argument(
        "--alert-file",
        default=str(DEFAULT_ALERT_FILE),
        help="预警意图 JSONL 输出路径"
    )
    parser.add_argument(
        "--model-id",
        default=str(DEFAULT_LOCAL_MODEL_DIR) if DEFAULT_LOCAL_MODEL_DIR.exists() else "google/timesfm-2.5-200m-pytorch",
        help="TimesFM 模型目录或 Hugging Face 模型 ID"
    )
    parser.add_argument(
        "--dpid",
        type=int,
        required=True,
        help="需要预测的交换机 DPID"
    )
    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="需要预测的交换机端口"
    )
    parser.add_argument(
        "--metric",
        choices=["load", "loss"],
        required=True,
        help="预测指标，load 或 loss"
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=24,
        help="预测未来小时数，第二阶段任务要求为 24"
    )
    parser.add_argument(
        "--hour-seconds",
        type=int,
        default=3600,
        help="一个预测小时对应的真实秒数。正式运行用 3600，实验演示可用 5 或 10"
    )
    parser.add_argument(
        "--min-context",
        type=int,
        default=8,
        help="TimesFM 最少上下文点数"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="可选阈值。load 常用 0.8，loss 常用 0.05"
    )

    args = parser.parse_args()

    engine = TimesFMEngine(
        model_id=args.model_id,
        max_context=1024,
        max_horizon=max(24, args.horizon)
    )

    result = engine.forecast_metric(
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
    alert = append_alert_intent(args.alert_file, result)

    print_summary(result, alert)


if __name__ == "__main__":
    main()