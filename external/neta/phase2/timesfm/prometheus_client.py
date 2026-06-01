# -*- coding: utf-8 -*-
"""
prometheus_client.py

作用：
1. 根据 device_id 和 metric 生成 PromQL。
2. 调用 Prometheus HTTP API query_range。
3. 把 Prometheus 返回结果转换成 TimesFM 可用的一维时序窗口。

示例：
device_id = AP-EXAM-302
metric = ap_load

生成 PromQL：
ap_load{device_id="AP-EXAM-302"}
"""

import os
import time
from typing import Dict, Any, List

import requests


DEFAULT_PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL",
    "http://127.0.0.1:9090"
)


def metric_to_promql_metric(metric: str) -> str:
    """
    外部 metric 转 Prometheus 指标名。

    约定：
    ap_load -> ap_load
    load    -> ap_load

    ap_loss -> ap_loss
    loss    -> ap_loss
    """
    if metric in ("ap_load", "load", "device_load"):
        return "ap_load"

    if metric in ("ap_loss", "loss", "packet_loss", "packet_loss_rate"):
        return "ap_loss"

    raise ValueError("不支持的 Prometheus metric: {}".format(metric))


def build_promql(device_id: str, metric: str) -> str:
    """
    构造 PromQL。

    示例：
    ap_load{device_id="AP-EXAM-302"}
    """
    prom_metric = metric_to_promql_metric(metric)

    return '{}{{device_id="{}"}}'.format(
        prom_metric,
        device_id
    )


class PrometheusClient:
    def __init__(self, base_url: str = None, timeout: int = 5):
        self.base_url = (base_url or DEFAULT_PROMETHEUS_URL).rstrip("/")
        self.timeout = timeout

    def health(self) -> Dict[str, Any]:
        """
        检查 Prometheus 是否可访问。
        """
        url = self.base_url + "/-/ready"

        r = requests.get(url, timeout=self.timeout)

        return {
            "ok": r.status_code == 200,
            "status_code": r.status_code,
            "text": r.text[:200]
        }

    def query_range(
        self,
        promql: str,
        start: int,
        end: int,
        step: str
    ) -> Dict[str, Any]:
        """
        调用 Prometheus query_range。

        参数：
        promql: PromQL 查询语句
        start: 起始 Unix 时间戳
        end:   结束 Unix 时间戳
        step:  查询步长，例如 5s、30s、60s
        """
        url = self.base_url + "/api/v1/query_range"

        params = {
            "query": promql,
            "start": start,
            "end": end,
            "step": step
        }

        r = requests.get(
            url,
            params=params,
            timeout=self.timeout
        )

        r.raise_for_status()

        data = r.json()

        if data.get("status") != "success":
            raise RuntimeError("Prometheus 查询失败: {}".format(data))

        return data

    def get_series(
        self,
        device_id: str,
        metric: str,
        lookback_seconds: int = 7200,
        step_seconds: int = 30
    ) -> Dict[str, Any]:
        """
        从 Prometheus 读取历史时序。

        默认读取过去 2 小时，步长 30 秒。

        返回：
        {
          "source": "prometheus",
          "promql": "...",
          "timestamps": [...],
          "values": [...]
        }
        """
        end = int(time.time())
        start = end - int(lookback_seconds)

        promql = build_promql(
            device_id=device_id,
            metric=metric
        )

        data = self.query_range(
            promql=promql,
            start=start,
            end=end,
            step=str(int(step_seconds)) + "s"
        )

        result = data.get("data", {}).get("result", [])

        if not result:
            raise ValueError(
                "Prometheus 没有返回数据。promql={}".format(promql)
            )

        values = result[0].get("values", [])

        timestamps: List[float] = []
        series_values: List[float] = []

        for item in values:
            if len(item) != 2:
                continue

            ts = float(item[0])
            value = float(item[1])

            timestamps.append(ts)
            series_values.append(value)

        if not series_values:
            raise ValueError(
                "Prometheus 返回空 values。promql={}".format(promql)
            )

        return {
            "source": "prometheus",
            "promql": promql,
            "device_id": device_id,
            "metric": metric,
            "timestamps": timestamps,
            "values": series_values
        }


def prometheus_available(base_url: str = None) -> bool:
    """
    简单判断 Prometheus 是否可访问。
    """
    try:
        client = PrometheusClient(base_url=base_url)
        result = client.health()
        return result.get("ok", False)
    except Exception:
        return False