"""TimesFM MCP Server。
时序大模型预测服务,端口默认 9003。

工具列表:
- forecast_metric:        单变量点预测,返回未来horizon时间内每个采样点的均值。
- forecast_quantile:      单变量分位数预测,返回 0.1/0.5/0.9 等分位线。
- detect_anomaly_window:  根据未来预测区间评估当前指标是否落在异常带。
"""

from __future__ import annotations

import math
import os
import statistics
import time
from dataclasses import dataclass
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from mcp_servers._common.http import make_async_client
from mcp_servers._common.logging import configure_logging

logger = configure_logging("TimesFmMCP")


@dataclass(slots=True)
class TimesFmMCPSettings:
    """TimesFM MCP 配置。"""

    host: str = os.getenv("TIMESFM_MCP_HOST", "0.0.0.0")
    port: int = int(os.getenv("TIMESFM_MCP_PORT", "9003"))
    transport: str = os.getenv("TIMESFM_MCP_TRANSPORT", "sse")
    request_timeout_seconds: float = float(os.getenv("MCP_REQUEST_TIMEOUT_SECONDS", "20"))

    # Prometheus历史数据源
    prometheus_base_url: str = os.getenv("PROMETHEUS_BASE_URL", "http://localhost:9090")

    # 远程 TimesFM 推理(HF Inference Endpoint 或兼容代理)
    # 例: https://api-inference.huggingface.co/models/google/timesfm-1.0-200m-pytorch
    remote_inference_url: str = os.getenv("TIMESFM_REMOTE_URL", "")
    remote_api_token: str = os.getenv("TIMESFM_REMOTE_TOKEN", os.getenv("HF_API_TOKEN", ""))
    remote_model_id: str = os.getenv("TIMESFM_REMOTE_MODEL", "google/timesfm-1.0-200m-pytorch")

    # 模型默认上下文/输出窗口
    default_context_points: int = int(os.getenv("TIMESFM_CONTEXT_POINTS", "96"))
    default_horizon_points: int = int(os.getenv("TIMESFM_HORIZON_POINTS", "24"))


settings = TimesFmMCPSettings()

mcp = FastMCP(
    name="TimesFmMCP",
    host=settings.host,
    port=settings.port,
    log_level="INFO",
)


# ----------------------------------------------------------------------------
# 历史数据采集
# ----------------------------------------------------------------------------

# 常用指标名 → PromQL模板
_METRIC_PROMQL_MAP: dict[str, str] = {
    "packet_loss": 'avg_over_time(device_packet_loss{{device_id="{dev}"}}[{step}s])',
    "cpu_load": 'avg_over_time(device_cpu_load{{device_id="{dev}"}}[{step}s])',
    "connections": 'avg_over_time(device_connections{{device_id="{dev}"}}[{step}s])',
    "ap_load": 'avg_over_time(ap_load{{ap_id="{dev}"}}[{step}s])',
    "bandwidth_in": 'avg_over_time(rate(if_in_octets{{device_id="{dev}"}}[1m])[{step}s:])',
    "bandwidth_out": 'avg_over_time(rate(if_out_octets{{device_id="{dev}"}}[1m])[{step}s:])',
}


def _build_promql(metric: str, device_id: str, step_seconds: int) -> str:
    """根据指标名生成 PromQL,未识别名则按"指标名{device_id=...}"兜底。"""

    template = _METRIC_PROMQL_MAP.get(metric)
    if template:
        return template.format(dev=device_id, step=max(60, step_seconds))
    return f'avg_over_time({metric}{{device_id="{device_id}"}}[{max(60, step_seconds)}s])'


async def _fetch_history(
    client: httpx.AsyncClient,
    device_id: str,
    metric: str,
    step_seconds: int,
    points: int,
) -> list[float]:
    """从Prometheus拉取最近points个采样点,返回浮点列表(缺失填 NaN)。"""

    promql = _build_promql(metric, device_id, step_seconds)
    end = time.time()
    start = end - step_seconds * points
    resp = await client.get(
        f"{settings.prometheus_base_url}/api/v1/query_range",
        params={"query": promql, "start": start, "end": end, "step": step_seconds},
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus 返回 status={payload.get('status')}")

    series = payload.get("data", {}).get("result", [])
    if not series:
        return []

    raw = series[0].get("values", []) if isinstance(series[0], dict) else []
    history: list[float] = []
    for _ts, val in raw:
        try:
            history.append(float(val))
        except (TypeError, ValueError):
            history.append(math.nan)
    return history


def _fillna(history: list[float]) -> list[float]:
    """把 NaN 用前向填充 + 后向填充补齐。"""

    if not history:
        return history
    cleaned = list(history)
    last_valid: float | None = None
    for i, v in enumerate(cleaned):
        if not math.isnan(v):
            last_valid = v
        elif last_valid is not None:
            cleaned[i] = last_valid
    # 反向再补一次,处理开头就 NaN 的情况
    last_valid = None
    for i in range(len(cleaned) - 1, -1, -1):
        if not math.isnan(cleaned[i]):
            last_valid = cleaned[i]
        elif last_valid is not None:
            cleaned[i] = last_valid
    # 仍然有 NaN(整段都是空),全部置 0
    cleaned = [0.0 if math.isnan(v) else v for v in cleaned]
    return cleaned

# ----------------------------------------------------------------------------
# 远程推理
# ----------------------------------------------------------------------------

async def _remote_forecast(
    history: list[float],
    horizon: int,
    quantiles: list[float] | None = None,
) -> dict[str, Any] | None:
    """调用远程 TimesFM 推理服务,失败时返回None让上层走兜底。
    """

    if not settings.remote_inference_url or not history:
        return None

    payload = {
        "inputs": history,
        "parameters": {
            "horizon": int(horizon),
            "quantiles": list(quantiles) if quantiles else [],
            "model_id": settings.remote_model_id,
        },
    }
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.remote_api_token:
        headers["Authorization"] = f"Bearer {settings.remote_api_token}"

    #远程 HF Inference 走外网,需要保留系统代理(trust_env=True)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            trust_env=True,
        ) as client:
            resp = await client.post(
                settings.remote_inference_url,
                json=payload,
                headers=headers,
            )
            if resp.status_code >= 400:
                logger.warning(
                    "Remote TimesFM returned %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None
            data = resp.json()
    except (httpx.TimeoutException, httpx.HTTPError, ValueError) as exc:
        logger.warning("Remote TimesFM call failed: %s: %s", type(exc).__name__, exc)
        return None

    # 兼容多种响应字段名
    forecast = (
        data.get("forecast")
        or data.get("predictions")
        or data.get("mean")
        or (data.get("data") or {}).get("forecast")
    )
    if not isinstance(forecast, list) or not forecast:
        logger.warning("Remote TimesFM response missing forecast array: keys=%s", list(data.keys()))
        return None

    quantile_map: dict[str, list[float]] = {}
    raw_q = data.get("quantiles") or (data.get("data") or {}).get("quantiles")
    if isinstance(raw_q, dict):
        for k, v in raw_q.items():
            if isinstance(v, list):
                try:
                    quantile_map[str(k)] = [float(x) for x in v]
                except (TypeError, ValueError):
                    continue

    try:
        forecast_clean = [float(x) for x in forecast][:horizon]
    except (TypeError, ValueError):
        return None

    return {
        "source": "remote",
        "forecast": forecast_clean,
        "quantiles": quantile_map,
    }


# ----------------------------------------------------------------------------
# TimesFM
# ----------------------------------------------------------------------------

_TIMESFM_MODEL = None

def _get_timesfm_model():
    global _TIMESFM_MODEL
    if _TIMESFM_MODEL is not None:
        return _TIMESFM_MODEL
    import timesfm, numpy as np
    model_path = "/root/models/timesfm-2.5-200m-pytorch"
    logger.info("Loading TimesFM from %s ...", model_path)
    _TIMESFM_MODEL = timesfm.TimesFM_2p5_200M_torch.from_pretrained(model_path)
    _TIMESFM_MODEL.compile(timesfm.ForecastConfig(max_context=512, max_horizon=24))
    logger.info("TimesFM model loaded.")
    return _TIMESFM_MODEL

def _local_timesfm_forecast(history, horizon):
    try:
        import numpy as np
        model = _get_timesfm_model()
        ctx = np.array(history[-256:], dtype=np.float32)
        pt, qt = model.forecast(int(horizon), [ctx])
        result = {"source": "timesfm-model", "forecast": pt[0].tolist(), "quantiles": {}}
        if qt is not None and len(qt) > 0:
            qarr = qt[0]
            if qarr.shape[1] > 9:
                result["quantiles"] = {"0.10": qarr[:,1].tolist(), "0.50": qarr[:,5].tolist(), "0.90": qarr[:,9].tolist()}
        logger.info("TimesFM forecast: %d points", len(result["forecast"]))
        return result
    except Exception as exc:
        logger.warning("TimesFM failed, fallback EWMA: %s", exc)
        return None

# EWMA
# ----------------------------------------------------------------------------

def _ewma(history: list[float], alpha: float = 0.3) -> list[float]:
    """指数加权移动平均序列。"""

    if not history:
        return []
    smooth = [history[0]]
    for v in history[1:]:
        smooth.append(alpha * v + (1 - alpha) * smooth[-1])
    return smooth


def _local_forecast(
    history: list[float],
    horizon: int,
    quantiles: list[float] | None = None,
) -> dict[str, Any]:
    """本地兜底预测。
    """

    if not history:
        zero_series = [0.0] * horizon
        empty_q = {f"{q:.2f}": list(zero_series) for q in (quantiles or [])}
        return {"source": "local-empty", "forecast": zero_series, "quantiles": empty_q}

    smooth = _ewma(history)
    baseline = smooth[-1]

    # 漂移估计:取最近 1/4 历史的差分均值
    tail = history[max(0, len(history) - max(4, len(history) // 4)) :]
    if len(tail) >= 2:
        diffs = [tail[i] - tail[i - 1] for i in range(1, len(tail))]
        drift = statistics.fmean(diffs)
    else:
        drift = 0.0

    # 残差标准差
    residuals = [h - s for h, s in zip(history, smooth)]
    if len(residuals) >= 2:
        sigma = statistics.pstdev(residuals)
    else:
        sigma = 0.0

    forecast = [baseline + drift * (i + 1) for i in range(horizon)]

    quantile_map: dict[str, list[float]] = {}
    if quantiles:
        # 用正态分布的近似 z 值表
        z_table = {
            0.05: -1.6449,
            0.10: -1.2816,
            0.25: -0.6745,
            0.50: 0.0,
            0.75: 0.6745,
            0.90: 1.2816,
            0.95: 1.6449,
        }
        for q in quantiles:
            qf = round(float(q), 2)
            z = z_table.get(qf)
            if z is None:
                # 找最近的
                z = min(z_table.items(), key=lambda kv: abs(kv[0] - qf))[1]
            quantile_map[f"{qf:.2f}"] = [
                forecast[i] + z * sigma * math.sqrt(i + 1) for i in range(horizon)
            ]

    return {"source": "local-ewma", "forecast": forecast, "quantiles": quantile_map}

# ----------------------------------------------------------------------------
# 公共工具入口
# ----------------------------------------------------------------------------

def _resolve_horizon_and_step(horizon_minutes: int, freq: str) -> tuple[int, int]:
    """根据期望的预测时长与采样频率计算 (horizon_points, step_seconds)。"""

    freq = (freq or "5m").strip().lower()
    if freq.endswith("m"):
        try:
            step_seconds = max(60, int(freq[:-1]) * 60)
        except ValueError:
            step_seconds = 300
    elif freq.endswith("s"):
        try:
            step_seconds = max(60, int(freq[:-1]))
        except ValueError:
            step_seconds = 60
    else:
        step_seconds = 300
    horizon_points = max(1, math.ceil(max(1, int(horizon_minutes)) * 60 / step_seconds))
    return horizon_points, step_seconds


@mcp.tool(
    description=(
        "对指定设备的某个指标进行未来 horizon 分钟的零样本时序预测,返回均值序列。"
        "freq 支持 '1m'/'5m'/'15m' 等。优先调用远程 TimesFM 模型。"
    )
)
async def forecast_metric(
    device_id: str,
    metric: str = "packet_loss",
    horizon_minutes: int = 60,
    freq: str = "5m",
) -> dict[str, Any]:
    """单变量点预测。"""

    logger.info(
        "Tool forecast_metric called. device=%s metric=%s horizon=%dm freq=%s",
        device_id, metric, horizon_minutes, freq,
    )
    if not device_id or not device_id.strip():
        return {"ok": False, "error": "device_id 不能为空"}

    horizon_points, step_seconds = _resolve_horizon_and_step(horizon_minutes, freq)
    context_points = settings.default_context_points

    #Prometheus历史数据走本地,禁用系统代理
    try:
        async with make_async_client(settings.request_timeout_seconds) as client:
            history_raw = await _fetch_history(
                client, device_id, metric, step_seconds, context_points
            )
    except httpx.TimeoutException:
        return {"ok": False, "error": "Prometheus 历史数据查询超时"}
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        logger.exception("forecast_metric history fetch failed.")
        return {"ok": False, "error": f"历史数据采集失败: {exc}"}

    history = _fillna(history_raw)
    if not history:
        logger.warning("No history available for device=%s metric=%s, using zero context.", device_id, metric)

    remote = await _remote_forecast(history, horizon_points)
    forecast_block = remote or _local_timesfm_forecast(history, horizon_points) or _local_forecast(history, horizon_points)

    return {
        "ok": True,
        "device_id": device_id,
        "metric": metric,
        "freq": freq,
        "step_seconds": step_seconds,
        "horizon_points": horizon_points,
        "history_points": len(history),
        "source": forecast_block["source"],
        "forecast": forecast_block["forecast"],
    }


@mcp.tool(
    description=(
        "对指定设备的某个指标做分位数预测,返回 quantiles 中每个分位线的序列。"
        "用于生成置信区间或阈值带。"
    )
)
async def forecast_quantile(
    device_id: str,
    metric: str = "packet_loss",
    horizon_minutes: int = 60,
    freq: str = "5m",
    quantiles: list[float] | None = None,
) -> dict[str, Any]:
    """分位数预测。"""

    qs = quantiles or [0.1, 0.5, 0.9]
    qs = [max(0.01, min(0.99, float(q))) for q in qs]

    logger.info(
        "Tool forecast_quantile called. device=%s metric=%s horizon=%dm freq=%s quantiles=%s",
        device_id, metric, horizon_minutes, freq, qs,
    )
    if not device_id or not device_id.strip():
        return {"ok": False, "error": "device_id 不能为空"}

    horizon_points, step_seconds = _resolve_horizon_and_step(horizon_minutes, freq)
    context_points = settings.default_context_points

    #拉Prometheus历史数据走本地
    try:
        async with make_async_client(settings.request_timeout_seconds) as client:
            history_raw = await _fetch_history(
                client, device_id, metric, step_seconds, context_points
            )
    except httpx.TimeoutException:
        return {"ok": False, "error": "Prometheus 历史数据查询超时"}
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        logger.exception("forecast_quantile history fetch failed.")
        return {"ok": False, "error": f"历史数据采集失败: {exc}"}

    history = _fillna(history_raw)
    remote = await _remote_forecast(history, horizon_points, quantiles=qs)
    if remote and remote.get("quantiles"):
        block = remote
    else:
        block = _local_forecast(history, horizon_points, quantiles=qs)

    return {
        "ok": True,
        "device_id": device_id,
        "metric": metric,
        "freq": freq,
        "step_seconds": step_seconds,
        "horizon_points": horizon_points,
        "history_points": len(history),
        "source": block["source"],
        "forecast": block["forecast"],
        "quantiles": block["quantiles"],
    }


@mcp.tool(
    description=(
        "结合预测置信区间评估当前指标是否处于异常带。返回risk_score(0~1)、"
        "is_anomaly与触发理由,供risk_review节点做风险定级。"
    )
)
async def detect_anomaly_window(
    device_id: str,
    metric: str = "packet_loss",
    horizon_minutes: int = 60,
    freq: str = "5m",
    upper_quantile: float = 0.9,
    threshold_override: float | None = None,
) -> dict[str, Any]:
    """基于预测置信区间的异常判定。"""

    logger.info(
        "Tool detect_anomaly_window called. device=%s metric=%s horizon=%dm upper_q=%s thr=%s",
        device_id, metric, horizon_minutes, upper_quantile, threshold_override,
    )
    if not device_id or not device_id.strip():
        return {"ok": False, "error": "device_id 不能为空"}

    upper_quantile = max(0.5, min(0.99, float(upper_quantile)))
    qs = [0.5, upper_quantile]

    forecast = await forecast_quantile(
        device_id=device_id,
        metric=metric,
        horizon_minutes=horizon_minutes,
        freq=freq,
        quantiles=qs,
    )
    if not forecast.get("ok"):
        return forecast

    upper_key = f"{upper_quantile:.2f}"
    median_key = "0.50"
    upper_band = forecast["quantiles"].get(upper_key, [])
    median_band = forecast["quantiles"].get(median_key, forecast["forecast"])
    if not upper_band or not median_band:
        return {
            "ok": False,
            "error": "未能取得预测分位数序列",
        }

    peak_upper = max(upper_band)
    peak_median = max(median_band)
    # 近期基线:取中位序列的均值,作为"未来预期常态"参考
    baseline_median = statistics.fmean(median_band) if median_band else peak_median

    #若显式传入 threshold_override,优先使用
    #否则用中位基线 *1.3 作为"显著抬升带",兼顾相对增长场景
    if threshold_override is not None:
        threshold = float(threshold_override)
    else:
        threshold = baseline_median * 1.3

    #risk_score:上分位峰值相对阈值的超出比例,clip到[0, 1]
    denom = max(abs(threshold), 1e-6)
    risk_score = max(0.0, min(1.0, (peak_upper - threshold) / denom))

    # is_anomaly: 上分位峰值越过阈值即视为异常
    is_anomaly = peak_upper >= threshold

    reasons: list[str] = []
    if peak_upper >= peak_median * 1.3:
        reasons.append(f"上分位预测峰值({peak_upper:.4f})显著高于中位({peak_median:.4f})")
    if threshold_override is not None and peak_upper >= threshold_override:
        reasons.append(f"上分位峰值已超过用户阈值 {threshold_override}")
    if threshold_override is None and peak_upper >= threshold:
        reasons.append(
            f"上分位峰值({peak_upper:.4f})超过基线 1.3 倍带({threshold:.4f})"
        )

    return {
        "ok": True,
        "device_id": device_id,
        "metric": metric,
        "horizon_minutes": horizon_minutes,
        "freq": freq,
        "upper_quantile": upper_quantile,
        "threshold": threshold,
        "threshold_source": "override" if threshold_override is not None else "baseline*1.3",
        "peak_upper": peak_upper,
        "peak_median": peak_median,
        "baseline_median": baseline_median,
        "is_anomaly": bool(is_anomaly),
        "risk_score": risk_score,
        "reasons": reasons,
        "source": forecast.get("source"),
    }


if __name__ == "__main__":
    logger.info(
        "Starting TimesFmMCP. transport=%s host=%s port=%s prom=%s remote=%s token=%s",
        settings.transport,
        settings.host,
        settings.port,
        settings.prometheus_base_url,
        settings.remote_inference_url or "<unset, fallback to local EWMA>",
        "set" if settings.remote_api_token else "unset",
    )
    mcp.run(transport=settings.transport)  # type: ignore[arg-type]
