#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
import math
import os
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

try:
    import uvicorn
except Exception:
    uvicorn = None


# =========================
# Paths & Config
# =========================

THIS_FILE = Path(__file__).resolve()

try:
    PROJECT_ROOT = THIS_FILE.parents[2]
except IndexError:
    PROJECT_ROOT = Path.cwd()

PHASE2_ROOT = PROJECT_ROOT / "phase2"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "timesfm-2.5-200m-pytorch"
DEFAULT_TELEMETRY_FILE = PHASE2_ROOT / "data" / "telemetry.csv"
DEFAULT_ALERTS_FILE = PHASE2_ROOT / "data" / "timesfm_alerts.jsonl"

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/")
TIMESFM_MODEL_DIR = Path(os.getenv("TIMESFM_MODEL_DIR", str(DEFAULT_MODEL_DIR))).expanduser()
TELEMETRY_FILE = Path(os.getenv("TELEMETRY_FILE", str(DEFAULT_TELEMETRY_FILE))).expanduser()
ALERTS_FILE = Path(os.getenv("ALERTS_FILE", str(DEFAULT_ALERTS_FILE))).expanduser()

USE_TIMESFM_MODEL = os.getenv("USE_TIMESFM_MODEL", "1") == "1"
ALLOW_HF_DOWNLOAD = os.getenv("ALLOW_HF_DOWNLOAD", "0") == "1"

SERVICE_NAME = "timesfm_ops_api"

METRIC_TO_PROM = {
    "ap_load": "ap_load",
    "load": "ap_load",
    "ap_latency": "ap_latency",
    "latency": "ap_latency",
    "ap_packet_loss": "ap_packet_loss",
    "packet_loss": "ap_packet_loss",
}

METRIC_TO_INTERNAL = {
    "ap_load": "load",
    "load": "load",
    "ap_latency": "latency",
    "latency": "latency",
    "ap_packet_loss": "packet_loss",
    "packet_loss": "packet_loss",
}

CSV_VALUE_COLUMNS = [
    "value",
    "load",
    "ap_load",
    "latency",
    "ap_latency",
    "packet_loss",
    "ap_packet_loss",
]

DEVICE_ID_COLUMNS = ["device_id", "device", "ap_id", "ap", "name"]
TIMESTAMP_COLUMNS = ["timestamp", "ts", "time", "datetime", "created_at"]


# =========================
# FastAPI App
# =========================

app = FastAPI(
    title="TimesFM Ops API",
    version="0.3.0",
    description="Prometheus 指标接入 TimesFM 预测，并触发主动防御状态机。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Pydantic Models
# =========================

class PredictRequest(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "example": {
                "device_id": "AP-EXAM-302",
                "metric": "ap_load",
                "horizon": 12,
                "threshold": 0.8,
            }
        },
    )

    device_id: str = Field(..., description="设备 ID，例如 AP-EXAM-302")
    metric: str = Field("ap_load", description="指标名，例如 ap_load")
    horizon: int = Field(12, ge=1, le=288, description="预测步数")

    hour_seconds: int = Field(5, ge=1, description="每个预测点代表的秒数")
    min_context: int = Field(3, ge=1, description="最小历史上下文点数")
    return_history_points: int = Field(24, ge=1, le=2000, description="返回给前端展示的历史点数量")

    lookback_seconds: int = Field(7200, ge=30, description="向前查询多少秒历史数据")
    prometheus_step_seconds: int = Field(30, ge=1, description="Prometheus query_range step")
    use_prometheus: bool = Field(True, description="是否优先使用 Prometheus")
    fallback_to_csv: bool = Field(True, description="Prometheus 无数据时是否回退 CSV")

    threshold: Optional[float] = Field(None, description="风险阈值")
    auto_write_alert: bool = Field(True, description="高风险时是否写入告警并触发主动防御")


class PredictResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    request_id: str
    timestamp: float
    timestamp_iso: str

    device_id: str
    device_name: Optional[str] = None
    zone_id: Optional[str] = None
    area_id: Optional[str] = None
    metric: str
    internal_metric: str
    dpid: Optional[Any] = None
    port: Optional[Any] = None

    horizon: int
    data_source: str

    history: List[float]
    forecast: List[float]
    upper_bound: List[float]
    lower_bound: List[float]

    risk: str
    alert: Optional[str] = None
    defense_status: str = "not_triggered"

    history_last_value: Optional[float] = None
    normalized_slope: float = 0.0
    raw_forecast: List[Dict[str, Any]] = Field(default_factory=list)
    data_source_info: Dict[str, Any] = Field(default_factory=dict)
    points: int = 0
    fallback_errors: List[str] = Field(default_factory=list)

    alert_written: bool = False
    alert_object: Optional[Dict[str, Any]] = None
    defense: Optional[Dict[str, Any]] = None


# =========================
# Active Defense State Machine
# =========================

class DefenseStage(str, Enum):
    NOT_TRIGGERED = "not_triggered"
    PREDICT_ALERT = "predict_alert"
    POLICY_GENERATING = "policy_generating"
    SANDBOX_VERIFYING = "sandbox_verifying"
    VERIFIED = "verified"
    DEPLOYED = "deployed"


DEFENSE_STATUS_TEXT = {
    DefenseStage.NOT_TRIGGERED.value: "未触发",
    DefenseStage.PREDICT_ALERT.value: "预测告警已触发",
    DefenseStage.POLICY_GENERATING.value: "策略生成中",
    DefenseStage.SANDBOX_VERIFYING.value: "沙盒验证中",
    DefenseStage.VERIFIED.value: "验证通过",
    DefenseStage.DEPLOYED.value: "已下发",
}

DEFENSE_STAGE_ORDER = [
    DefenseStage.POLICY_GENERATING.value,
    DefenseStage.SANDBOX_VERIFYING.value,
    DefenseStage.VERIFIED.value,
    DefenseStage.DEPLOYED.value,
]

DEFENSE_STATE_STORE: Dict[str, Dict[str, Any]] = {}


# =========================
# Common Utils
# =========================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except Exception:
        return None


def as_float_list(values: Any) -> List[float]:
    if values is None:
        return []

    result: List[float] = []

    for item in values:
        try:
            if isinstance(item, dict):
                if "point" in item:
                    parsed = safe_float(item["point"])
                elif "value" in item:
                    parsed = safe_float(item["value"])
                else:
                    parsed = None
            else:
                parsed = safe_float(item)

            if parsed is not None:
                result.append(parsed)
        except Exception:
            continue

    return result


def metric_to_prometheus(metric: str) -> str:
    return METRIC_TO_PROM.get(metric, metric)


def metric_to_internal(metric: str) -> str:
    return METRIC_TO_INTERNAL.get(metric, metric)


def escape_promql_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_promql(metric: str, device_id: Optional[str] = None) -> str:
    prom_metric = metric_to_prometheus(metric)

    if device_id:
        escaped_device = escape_promql_label_value(device_id)
        return f'{prom_metric}{{device_id="{escaped_device}"}}'

    return prom_metric


def parse_timestamp(value: Any) -> Optional[float]:
    if value is None:
        return None

    number = safe_float(value)
    if number is not None:
        return number

    text = str(value).strip()
    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def infer_threshold(values: List[float]) -> float:
    clean = [abs(v) for v in values if safe_float(v) is not None]

    if not clean:
        return 0.8

    max_value = max(clean)

    if max_value <= 1.5:
        return 0.8

    return 80.0


def compute_normalized_slope(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0

    first = values[0]
    last = values[-1]
    denom = max(abs(first), abs(last), 1.0)

    return (last - first) / denom / max(1, len(values) - 1)


def left_pad_history(history: List[float], min_context: int) -> List[float]:
    if len(history) >= min_context:
        return history

    if not history:
        return [0.0] * min_context

    return [history[0]] * (min_context - len(history)) + history


# =========================
# Prometheus Data Source
# =========================

def prometheus_get(path: str, params: Dict[str, Any], timeout: int = 5) -> Dict[str, Any]:
    url = f"{PROMETHEUS_URL}{path}"
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus 返回非 success: {payload}")

    return payload.get("data", {})


def fetch_prometheus_range(
    device_id: str,
    metric: str,
    lookback_seconds: int,
    step_seconds: int,
) -> Tuple[List[float], Dict[str, Any], Dict[str, Any]]:
    end = time.time()
    start = end - lookback_seconds
    promql = build_promql(metric, device_id)

    data = prometheus_get(
        "/api/v1/query_range",
        params={
            "query": promql,
            "start": start,
            "end": end,
            "step": step_seconds,
        },
    )

    result = data.get("result", [])

    if not result:
        return [], {}, {
            "source": "prometheus",
            "prometheus_url": PROMETHEUS_URL,
            "promql": promql,
            "points": 0,
        }

    series = max(result, key=lambda item: len(item.get("values", [])))
    labels = dict(series.get("metric", {}))

    values: List[float] = []

    for pair in series.get("values", []):
        if not isinstance(pair, list) or len(pair) < 2:
            continue

        parsed = safe_float(pair[1])

        if parsed is not None:
            values.append(parsed)

    return values, labels, {
        "source": "prometheus",
        "prometheus_url": PROMETHEUS_URL,
        "promql": promql,
        "points": len(values),
    }


def fetch_prometheus_instant(
    device_id: str,
    metric: str,
) -> Tuple[List[float], Dict[str, Any], Dict[str, Any]]:
    promql = build_promql(metric, device_id)
    data = prometheus_get("/api/v1/query", params={"query": promql})

    result = data.get("result", [])

    if not result:
        return [], {}, {
            "source": "prometheus_instant",
            "prometheus_url": PROMETHEUS_URL,
            "promql": promql,
            "points": 0,
        }

    series = result[0]
    labels = dict(series.get("metric", {}))
    value_pair = series.get("value", [])

    value = safe_float(value_pair[1]) if len(value_pair) >= 2 else None
    values = [value] if value is not None else []

    return values, labels, {
        "source": "prometheus_instant",
        "prometheus_url": PROMETHEUS_URL,
        "promql": promql,
        "points": len(values),
    }


def fetch_prometheus_devices(metric: str) -> List[Dict[str, Any]]:
    prom_metric = metric_to_prometheus(metric)
    data = prometheus_get("/api/v1/query", params={"query": prom_metric})

    result = data.get("result", [])
    devices: Dict[str, Dict[str, Any]] = {}

    for item in result:
        labels = dict(item.get("metric", {}))
        device_id = labels.get("device_id") or labels.get("device") or labels.get("ap_id")

        if not device_id:
            continue

        value_pair = item.get("value", [])
        value = safe_float(value_pair[1]) if len(value_pair) >= 2 else None

        devices[device_id] = {
            "device_id": device_id,
            "device_name": labels.get("device_name") or labels.get("name") or device_id,
            "zone_id": labels.get("zone_id"),
            "area_id": labels.get("area_id"),
            "dpid": labels.get("dpid"),
            "port": labels.get("port"),
            "role": labels.get("role"),
            "metric": prom_metric,
            "value": value,
            "labels": labels,
        }

    return sorted(devices.values(), key=lambda x: x["device_id"])


# =========================
# CSV Data Source
# =========================

def read_csv_rows() -> List[Dict[str, Any]]:
    if not TELEMETRY_FILE.exists():
        return []

    with TELEMETRY_FILE.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def row_device_id(row: Dict[str, Any]) -> Optional[str]:
    for column in DEVICE_ID_COLUMNS:
        value = row.get(column)

        if value:
            return str(value)

    return None


def row_timestamp(row: Dict[str, Any], index: int) -> float:
    for column in TIMESTAMP_COLUMNS:
        parsed = parse_timestamp(row.get(column))

        if parsed is not None:
            return parsed

    return float(index)


def row_metric_matches(row: Dict[str, Any], metric: str, internal_metric: str) -> bool:
    row_metric = row.get("metric") or row.get("metric_name") or row.get("name")

    if not row_metric:
        return True

    return str(row_metric) in {metric, internal_metric, metric_to_prometheus(metric)}


def row_value_for_metric(row: Dict[str, Any], metric: str, internal_metric: str) -> Optional[float]:
    candidates = [metric, internal_metric, metric_to_prometheus(metric)] + CSV_VALUE_COLUMNS
    seen = set()

    for column in candidates:
        if column in seen:
            continue

        seen.add(column)

        if column in row and row[column] not in (None, ""):
            parsed = safe_float(row[column])

            if parsed is not None:
                return parsed

    return None


def fetch_csv_series(
    device_id: str,
    metric: str,
    max_points: int,
) -> Tuple[List[float], Dict[str, Any], Dict[str, Any]]:
    internal_metric = metric_to_internal(metric)
    rows = read_csv_rows()

    matched: List[Tuple[float, float, Dict[str, Any]]] = []

    for index, row in enumerate(rows):
        current_device_id = row_device_id(row)

        if current_device_id and current_device_id != device_id:
            continue

        if not row_metric_matches(row, metric, internal_metric):
            continue

        value = row_value_for_metric(row, metric, internal_metric)

        if value is None:
            continue

        matched.append((row_timestamp(row, index), value, row))

    matched.sort(key=lambda item: item[0])

    if max_points > 0:
        matched = matched[-max_points:]

    values = [item[1] for item in matched]
    labels: Dict[str, Any] = {"device_id": device_id}

    if matched:
        last_row = matched[-1][2]

        for key in ["device_name", "name", "zone_id", "area_id", "dpid", "port", "role"]:
            if last_row.get(key):
                labels[key] = last_row.get(key)

    return values, labels, {
        "source": "csv",
        "telemetry_file": str(TELEMETRY_FILE),
        "points": len(values),
    }


def fetch_csv_devices(metric: str) -> List[Dict[str, Any]]:
    internal_metric = metric_to_internal(metric)
    rows = read_csv_rows()
    devices: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        if not row_metric_matches(row, metric, internal_metric):
            continue

        device_id = row_device_id(row)

        if not device_id:
            continue

        value = row_value_for_metric(row, metric, internal_metric)

        devices[device_id] = {
            "device_id": device_id,
            "device_name": row.get("device_name") or row.get("name") or device_id,
            "zone_id": row.get("zone_id"),
            "area_id": row.get("area_id"),
            "dpid": row.get("dpid"),
            "port": row.get("port"),
            "role": row.get("role"),
            "metric": metric,
            "value": value,
        }

    return sorted(devices.values(), key=lambda x: x["device_id"])


# =========================
# History Collection
# =========================

def collect_history(req: PredictRequest) -> Tuple[List[float], Dict[str, Any], str, Dict[str, Any], List[str]]:
    errors: List[str] = []

    if req.use_prometheus:
        try:
            values, labels, info = fetch_prometheus_range(
                device_id=req.device_id,
                metric=req.metric,
                lookback_seconds=req.lookback_seconds,
                step_seconds=req.prometheus_step_seconds,
            )

            if values:
                return values, labels, "prometheus", info, errors

        except Exception as exc:
            errors.append(f"prometheus_range_error: {exc}")

        try:
            values, labels, info = fetch_prometheus_instant(
                device_id=req.device_id,
                metric=req.metric,
            )

            if values:
                return values, labels, "prometheus", info, errors

        except Exception as exc:
            errors.append(f"prometheus_instant_error: {exc}")

    if req.fallback_to_csv:
        try:
            values, labels, info = fetch_csv_series(
                device_id=req.device_id,
                metric=req.metric,
                max_points=max(req.return_history_points, req.min_context, 24),
            )

            if values:
                return values, labels, "csv", info, errors

        except Exception as exc:
            errors.append(f"csv_error: {exc}")

    generated = [0.0] * max(req.min_context, req.return_history_points)

    info = {
        "source": "generated_empty",
        "reason": "Prometheus 和 CSV 都没有取到数据，已生成 0 序列兜底",
        "points": len(generated),
    }

    errors.append("no_real_history_data_found")

    return generated, {"device_id": req.device_id}, "generated_empty", info, errors


# =========================
# TimesFM / Forecast
# =========================

_TIMESFM_MODEL: Any = None
_TIMESFM_MODEL_ERROR: Optional[str] = None


def naive_forecast(history: List[float], horizon: int) -> List[Dict[str, Any]]:
    clean = [float(x) for x in history if safe_float(x) is not None]

    if not clean:
        clean = [0.0]

    recent = clean[-min(len(clean), 24):]
    last_value = recent[-1]

    deltas = [recent[i] - recent[i - 1] for i in range(1, len(recent))]

    if deltas:
        recent_deltas = deltas[-min(len(deltas), 6):]
        slope = sum(recent_deltas) / len(recent_deltas)
    else:
        slope = 0.0

    mean = sum(recent) / len(recent)
    variance = sum((x - mean) ** 2 for x in recent) / max(1, len(recent) - 1)
    std = math.sqrt(variance)

    base_band = max(std, abs(slope) * 2.0, abs(last_value) * 0.02, 1e-9)

    output: List[Dict[str, Any]] = []

    for future_hour in range(1, horizon + 1):
        point = max(0.0, last_value + slope * future_hour)
        band = base_band * (1.0 + future_hour / max(1, horizon))

        q10 = max(0.0, point - band)
        q50 = point
        q90 = point + band

        output.append(
            {
                "future_hour": future_hour,
                "point": point,
                "q10": q10,
                "q50": q50,
                "q90": q90,
            }
        )

    return output


def get_timesfm_model(horizon: int) -> Any:
    global _TIMESFM_MODEL, _TIMESFM_MODEL_ERROR

    if _TIMESFM_MODEL is not None:
        return _TIMESFM_MODEL

    if _TIMESFM_MODEL_ERROR is not None:
        raise RuntimeError(_TIMESFM_MODEL_ERROR)

    try:
        import timesfm  # type: ignore
    except Exception as exc:
        _TIMESFM_MODEL_ERROR = f"import timesfm failed: {exc}"
        raise RuntimeError(_TIMESFM_MODEL_ERROR)

    checkpoint_candidates: List[Any] = []
    checkpoint_errors: List[str] = []

    if TIMESFM_MODEL_DIR.exists():
        for kwargs in [
            {"path": str(TIMESFM_MODEL_DIR)},
            {"local_dir": str(TIMESFM_MODEL_DIR)},
        ]:
            try:
                checkpoint_candidates.append(timesfm.TimesFmCheckpoint(**kwargs))
            except Exception as exc:
                checkpoint_errors.append(f"checkpoint {kwargs} failed: {exc}")

    if ALLOW_HF_DOWNLOAD:
        for kwargs in [
            {"huggingface_repo_id": "google/timesfm-2.5-200m-pytorch"},
            {"huggingface_repo_id": "google/timesfm-2.0-500m-pytorch"},
            {"huggingface_repo_id": "google/timesfm-1.0-200m"},
        ]:
            try:
                checkpoint_candidates.append(timesfm.TimesFmCheckpoint(**kwargs))
            except Exception as exc:
                checkpoint_errors.append(f"checkpoint {kwargs} failed: {exc}")

    hparams_candidates: List[Any] = []
    hparams_errors: List[str] = []

    for kwargs in [
        {
            "backend": "cpu",
            "per_core_batch_size": 1,
            "horizon_len": max(1, horizon),
            "context_len": 512,
        },
        {
            "backend": "cpu",
            "per_core_batch_size": 1,
            "horizon_len": max(1, horizon),
        },
        {
            "backend": "cpu",
            "horizon_len": max(1, horizon),
        },
    ]:
        try:
            hparams_candidates.append(timesfm.TimesFmHparams(**kwargs))
        except Exception as exc:
            hparams_errors.append(f"hparams {kwargs} failed: {exc}")

    model_errors: List[str] = []

    for hparams in hparams_candidates:
        for checkpoint in checkpoint_candidates:
            try:
                _TIMESFM_MODEL = timesfm.TimesFm(hparams=hparams, checkpoint=checkpoint)
                return _TIMESFM_MODEL
            except Exception as exc:
                model_errors.append(str(exc))

    _TIMESFM_MODEL_ERROR = "; ".join(
        checkpoint_errors[-3:] + hparams_errors[-3:] + model_errors[-3:]
    ) or "unknown timesfm init error"

    raise RuntimeError(_TIMESFM_MODEL_ERROR)


def forecast_with_timesfm(history: List[float], horizon: int) -> List[Dict[str, Any]]:
    import numpy as np  # type: ignore

    model = get_timesfm_model(horizon)
    arr = np.array(history, dtype=np.float32)

    result = model.forecast([arr], freq=[0])

    if isinstance(result, tuple) and len(result) >= 2:
        point_forecast = result[0]
        quantile_forecast = result[1]
    else:
        point_forecast = result
        quantile_forecast = None

    points = list(point_forecast[0])[:horizon]
    output: List[Dict[str, Any]] = []

    for index, point_value in enumerate(points):
        point = float(point_value)
        q10 = point
        q50 = point
        q90 = point

        try:
            if quantile_forecast is not None:
                row = list(quantile_forecast[0][index])

                if len(row) >= 3:
                    q10 = float(row[0])
                    q50 = float(row[len(row) // 2])
                    q90 = float(row[-1])
        except Exception:
            pass

        output.append(
            {
                "future_hour": index + 1,
                "point": point,
                "q10": q10,
                "q50": q50,
                "q90": q90,
            }
        )

    if len(output) < horizon:
        fallback = naive_forecast(
            history + [item["point"] for item in output],
            horizon - len(output),
        )

        output.extend(fallback)

        for idx, item in enumerate(output):
            item["future_hour"] = idx + 1

    return output[:horizon]


def forecast_series(history: List[float], horizon: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    errors: List[str] = []

    if USE_TIMESFM_MODEL:
        try:
            raw = forecast_with_timesfm(history, horizon)

            return raw, {
                "model": "timesfm",
                "model_dir": str(TIMESFM_MODEL_DIR),
                "fallback": False,
            }, errors

        except Exception as exc:
            errors.append(f"timesfm_error: {exc}")

    raw = naive_forecast(history, horizon)

    return raw, {
        "model": "fallback_linear_forecast",
        "model_dir": str(TIMESFM_MODEL_DIR),
        "fallback": True,
    }, errors


# =========================
# Risk / Alert / Defense
# =========================

def evaluate_prediction_risk(
    forecast: Any,
    upper_bound: Any,
    threshold: float,
) -> Tuple[str, float, float]:
    forecast_values = as_float_list(forecast)
    upper_values = as_float_list(upper_bound)

    max_forecast = max(forecast_values) if forecast_values else 0.0
    max_upper = max(upper_values) if upper_values else max_forecast

    if max_forecast >= threshold or max_upper >= threshold:
        return "HIGH", max_forecast, max_upper

    if max_upper >= threshold * 0.85:
        return "MEDIUM", max_forecast, max_upper

    return "LOW", max_forecast, max_upper


def build_prediction_alert(
    device_id: str,
    device_name: Optional[str],
    zone_id: Optional[str],
    area_id: Optional[str],
    metric: str,
    horizon: int,
    threshold: float,
    max_forecast: float,
    max_upper: float,
) -> Dict[str, Any]:
    alert_id = f"alert-{uuid4().hex[:12]}"
    target_name = device_name or device_id

    return {
        "alert_id": alert_id,
        "alert_type": "timesfm_predict_overload",
        "level": "HIGH",
        "device_id": device_id,
        "device_name": target_name,
        "zone_id": zone_id,
        "area_id": area_id,
        "metric": metric,
        "horizon": horizon,
        "threshold": threshold,
        "max_forecast": max_forecast,
        "max_upper_bound": max_upper,
        "message": f"未来预测窗口内，{target_name} 的 {metric} 预计超过阈值，存在过载风险",
        "created_at": utc_now_iso(),
    }


def append_alert_jsonl(alert: Dict[str, Any]) -> None:
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with ALERTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(alert, ensure_ascii=False) + "\n")


def generate_defense_policy(alert: Dict[str, Any]) -> Dict[str, Any]:
    policy_id = f"policy-{uuid4().hex[:12]}"

    return {
        "policy_id": policy_id,
        "policy_type": "load_balance",
        "target_device_id": alert["device_id"],
        "target_device_name": alert.get("device_name"),
        "metric": alert["metric"],
        "reason": alert["message"],
        "actions": [
            {
                "action": "redirect_new_clients",
                "description": "将新接入用户优先引导到同区域低负载 AP",
            },
            {
                "action": "rate_limit_non_critical_traffic",
                "description": "限制非关键业务流量，降低目标 AP 负载",
            },
            {
                "action": "increase_monitoring_frequency",
                "description": "提高目标 AP 指标采样频率，持续观察负载变化",
            },
        ],
        "sandbox_required": True,
        "deployed": False,
        "created_at": utc_now_iso(),
    }


def trigger_defense_by_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    device_id = alert["device_id"]
    policy = generate_defense_policy(alert)

    state = {
        "triggered": True,
        "device_id": device_id,
        "status": DefenseStage.POLICY_GENERATING.value,
        "status_text": DEFENSE_STATUS_TEXT[DefenseStage.POLICY_GENERATING.value],
        "alert": alert,
        "policy": policy,
        "timeline": [
            {
                "stage": DefenseStage.PREDICT_ALERT.value,
                "status_text": DEFENSE_STATUS_TEXT[DefenseStage.PREDICT_ALERT.value],
                "time": utc_now_iso(),
            },
            {
                "stage": DefenseStage.POLICY_GENERATING.value,
                "status_text": DEFENSE_STATUS_TEXT[DefenseStage.POLICY_GENERATING.value],
                "time": utc_now_iso(),
            },
        ],
        "updated_at": utc_now_iso(),
    }

    DEFENSE_STATE_STORE[device_id] = state

    return state


def get_defense_state(device_id: str) -> Dict[str, Any]:
    state = DEFENSE_STATE_STORE.get(device_id)

    if state:
        return state

    return {
        "triggered": False,
        "device_id": device_id,
        "status": DefenseStage.NOT_TRIGGERED.value,
        "status_text": DEFENSE_STATUS_TEXT[DefenseStage.NOT_TRIGGERED.value],
        "alert": None,
        "policy": None,
        "timeline": [],
        "updated_at": utc_now_iso(),
    }


def mock_advance_defense_stage(device_id: str) -> Dict[str, Any]:
    state = DEFENSE_STATE_STORE.get(device_id)

    if not state:
        return get_defense_state(device_id)

    current_status = state.get("status", DefenseStage.POLICY_GENERATING.value)

    if current_status not in DEFENSE_STAGE_ORDER:
        next_status = DefenseStage.POLICY_GENERATING.value
    else:
        current_index = DEFENSE_STAGE_ORDER.index(current_status)
        next_index = min(current_index + 1, len(DEFENSE_STAGE_ORDER) - 1)
        next_status = DEFENSE_STAGE_ORDER[next_index]

    state["status"] = next_status
    state["status_text"] = DEFENSE_STATUS_TEXT[next_status]
    state["updated_at"] = utc_now_iso()

    if next_status == DefenseStage.DEPLOYED.value and state.get("policy"):
        state["policy"]["deployed"] = True
        state["policy"]["deployed_at"] = utc_now_iso()

    state.setdefault("timeline", []).append(
        {
            "stage": next_status,
            "status_text": DEFENSE_STATUS_TEXT[next_status],
            "time": utc_now_iso(),
        }
    )

    DEFENSE_STATE_STORE[device_id] = state

    return state


def read_recent_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    if not ALERTS_FILE.exists():
        return []

    lines = ALERTS_FILE.read_text(encoding="utf-8").splitlines()
    output: List[Dict[str, Any]] = []

    for line in lines[-limit:]:
        try:
            output.append(json.loads(line))
        except Exception:
            continue

    return output


# =========================
# API Routes
# =========================

@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "endpoints": [
            "GET /health",
            "GET /api/ops/devices",
            "POST /api/ops/predict",
            "GET /api/ops/defense/status",
            "POST /api/ops/defense/mock/advance",
            "GET /api/ops/alerts",
        ],
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "timestamp": time.time(),
        "timestamp_iso": utc_now_iso(),
        "model_dir": str(TIMESFM_MODEL_DIR),
        "model_dir_exists": TIMESFM_MODEL_DIR.exists(),
        "telemetry_file": str(TELEMETRY_FILE),
        "telemetry_file_exists": TELEMETRY_FILE.exists(),
        "alerts_file": str(ALERTS_FILE),
        "prometheus_url": PROMETHEUS_URL,
        "use_timesfm_model": USE_TIMESFM_MODEL,
        "allow_hf_download": ALLOW_HF_DOWNLOAD,
    }


@app.get("/api/ops/devices")
def list_ops_devices(metric: str = Query("ap_load", description="Prometheus 指标名")) -> Dict[str, Any]:
    errors: List[str] = []

    try:
        items = fetch_prometheus_devices(metric)

        if items:
            return {
                "source": "prometheus",
                "metric": metric,
                "count": len(items),
                "items": items,
                "errors": errors,
            }

    except Exception as exc:
        errors.append(f"prometheus_devices_error: {exc}")

    try:
        items = fetch_csv_devices(metric)

        return {
            "source": "csv",
            "metric": metric,
            "count": len(items),
            "items": items,
            "errors": errors,
        }

    except Exception as exc:
        errors.append(f"csv_devices_error: {exc}")

    return {
        "source": "none",
        "metric": metric,
        "count": 0,
        "items": [],
        "errors": errors,
    }


@app.post("/api/ops/predict", response_model=PredictResponse)
def predict_ops(req: PredictRequest) -> PredictResponse:
    request_id = f"pred-{int(time.time() * 1000)}"
    now_ts = time.time()
    now_iso = utc_now_iso()

    history, labels, data_source, data_source_info, fallback_errors = collect_history(req)
    original_points = len(history)

    history = left_pad_history(history, req.min_context)
    internal_metric = metric_to_internal(req.metric)

    device_name = labels.get("device_name") or labels.get("name") or req.device_id
    zone_id = labels.get("zone_id")
    area_id = labels.get("area_id")
    dpid = labels.get("dpid")
    port = labels.get("port")

    raw_forecast, model_info, model_errors = forecast_series(history, req.horizon)
    fallback_errors.extend(model_errors)

    forecast = [float(item.get("point", 0.0)) for item in raw_forecast]
    lower_bound = [float(item.get("q10", item.get("point", 0.0))) for item in raw_forecast]
    upper_bound = [float(item.get("q90", item.get("point", 0.0))) for item in raw_forecast]

    threshold_value = req.threshold if req.threshold is not None else infer_threshold(history + forecast + upper_bound)

    risk, max_forecast, max_upper = evaluate_prediction_risk(
        forecast=forecast,
        upper_bound=upper_bound,
        threshold=threshold_value,
    )

    alert_text = None
    alert_object = None
    alert_written = False
    defense_status = DefenseStage.NOT_TRIGGERED.value
    defense = None

    if risk == "HIGH":
        alert_object = build_prediction_alert(
            device_id=req.device_id,
            device_name=device_name,
            zone_id=zone_id,
            area_id=area_id,
            metric=req.metric,
            horizon=req.horizon,
            threshold=threshold_value,
            max_forecast=max_forecast,
            max_upper=max_upper,
        )

        alert_text = alert_object["message"]
        defense_status = DefenseStage.PREDICT_ALERT.value

        if req.auto_write_alert:
            append_alert_jsonl(alert_object)
            defense = trigger_defense_by_alert(alert_object)
            alert_written = True
            defense_status = defense["status"]

    data_source_info = {
        **data_source_info,
        "model_info": model_info,
        "labels": labels,
        "threshold": threshold_value,
    }

    response_history = history[-req.return_history_points:]

    return PredictResponse(
        request_id=request_id,
        timestamp=now_ts,
        timestamp_iso=now_iso,
        device_id=req.device_id,
        device_name=device_name,
        zone_id=zone_id,
        area_id=area_id,
        metric=req.metric,
        internal_metric=internal_metric,
        dpid=dpid,
        port=port,
        horizon=req.horizon,
        data_source=data_source,
        history=response_history,
        forecast=forecast,
        upper_bound=upper_bound,
        lower_bound=lower_bound,
        risk=risk,
        alert=alert_text,
        defense_status=defense_status,
        history_last_value=response_history[-1] if response_history else None,
        normalized_slope=compute_normalized_slope(response_history),
        raw_forecast=raw_forecast,
        data_source_info=data_source_info,
        points=original_points,
        fallback_errors=fallback_errors,
        alert_written=alert_written,
        alert_object=alert_object,
        defense=defense,
    )


@app.get("/api/ops/defense/status")
def get_ops_defense_status(device_id: Optional[str] = Query(None, description="设备 ID")) -> Dict[str, Any]:
    if device_id:
        return get_defense_state(device_id)

    return {
        "count": len(DEFENSE_STATE_STORE),
        "items": list(DEFENSE_STATE_STORE.values()),
    }


@app.post("/api/ops/defense/mock/advance")
def mock_advance_ops_defense(device_id: str = Query(..., description="设备 ID")) -> Dict[str, Any]:
    return mock_advance_defense_stage(device_id)


@app.post("/api/ops/defense/mock/reset")
def mock_reset_ops_defense(device_id: Optional[str] = Query(None, description="设备 ID；不传则清空全部")) -> Dict[str, Any]:
    if device_id:
        DEFENSE_STATE_STORE.pop(device_id, None)
        return {
            "ok": True,
            "reset": device_id,
        }

    DEFENSE_STATE_STORE.clear()

    return {
        "ok": True,
        "reset": "all",
    }


@app.get("/api/ops/alerts")
def list_ops_alerts(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    items = read_recent_alerts(limit=limit)

    return {
        "count": len(items),
        "items": items,
        "alerts_file": str(ALERTS_FILE),
    }


# =========================
# Main
# =========================

if __name__ == "__main__":
    if uvicorn is None:
        raise RuntimeError("uvicorn 没有安装，请先安装 uvicorn")

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    uvicorn.run(app, host=host, port=port)
