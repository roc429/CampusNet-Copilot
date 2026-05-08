"""统一httpx 客户端工厂。

Windows / 公司网络下常见的"系统代理劫持 localhost"问题:
- httpx.AsyncClient() 默认 trust_env=True,会读 HTTP_PROXY/HTTPS_PROXY 环境变量
- Clash / V2Ray / 公司代理通常对 127.0.0.1 也走代理,导致 Prometheus/Grafana/Pushgateway
  这些本地服务返回 502/超时

本模块统一管理 trust_env 行为,默认禁用环境代理(DISABLE_ENV_PROXY=true),
与 app/config.py 的约定一致。需要走代理(如调远程 HF Inference)时再用专用 client。
"""

from __future__ import annotations

import os

import httpx


def disable_env_proxy() -> bool:
    """读取 DISABLE_ENV_PROXY 环境变量,默认 True(关闭系统代理)。"""

    return os.getenv("DISABLE_ENV_PROXY", "true").lower() in {"1", "true", "yes", "on"}


def make_async_client(
    timeout_seconds: float = 10.0,
    *,
    trust_env: bool | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """创建一个对 localhost 友好的 httpx.AsyncClient。

    Args:
        timeout_seconds: 总超时时间。
        trust_env:       None 表示按 DISABLE_ENV_PROXY 决定;显式传 True/False 覆盖。
        headers:         默认请求头。
    """

    if trust_env is None:
        trust_env = not disable_env_proxy()
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        trust_env=trust_env,
        headers=headers,
    )
