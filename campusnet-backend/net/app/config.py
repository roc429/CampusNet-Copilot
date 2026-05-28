"""全局配置模块。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    """应用运行配置。

    Attributes:
        base_url: OpenAI 兼容接口地址（可指向 vLLM / 百炼）。
        model: 兼容字段，作为 fast/deep 模型的默认值。
        mcp_base_url: 兼容旧版 FastAPI MCP 地址（保留字段）。
        netbox_mcp_sse_url:     NetBox 官方 MCP Server 的 SSE 地址。
        campus_mcp_sse_url:     Campus MCP Server (校园业务) 的 SSE 地址。
        prometheus_mcp_sse_url: Prometheus MCP Server 的 SSE 地址(新拆分)。
        grafana_mcp_sse_url:    Grafana MCP Server 的 SSE 地址(新拆分)。
        timesfm_mcp_sse_url:    TimesFM MCP Server 的 SSE 地址(新建)。
        mcp_sse_read_timeout: MCP SSE 长连接读超时，单位秒。
        request_timeout: 模型与 HTTP 请求超时时间，单位秒。
        llm_strict: 为 True 时,LLM 调用异常直接抛出，便于调试。
        netbox_url: NetBox REST API 基础地址。
        netbox_token: NetBox API Token
        timesfm_remote_url:   远程 TimesFM 推理端点(HF Inference Endpoint 或自部署代理)。
        timesfm_remote_token: 远程 TimesFM 推理 Token(可与 HF_API_TOKEN 共用)。
        rag_mock_enabled: 未接入真实知识库时是否启用内置 mock RAG。
        telemetry_mock_enabled: 是否启用随机遥测事件，默认关闭，避免干扰用户报告。
        forecast_agent_enabled: 是否启动后台预测 Agent。
    """

    base_url: str = os.getenv("BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    model: str = os.getenv("MODEL", "mimo-v2.5-pro")
    mcp_base_url: str = os.getenv("MCP_BASE_URL", "http://localhost:9000")

    # MCP Server 端点(各端点为空字符串时,manager 自动跳过注册)
    netbox_mcp_sse_url: str = os.getenv("NETBOX_MCP_SSE_URL", "http://localhost:7001/mcp")
    campus_mcp_sse_url: str = os.getenv("CAMPUS_MCP_SSE_URL", "http://localhost:9000/sse")
    prometheus_mcp_sse_url: str = os.getenv("PROMETHEUS_MCP_SSE_URL", "http://localhost:9001/sse")
    grafana_mcp_sse_url: str = os.getenv("GRAFANA_MCP_SSE_URL", "http://localhost:9002/sse")
    timesfm_mcp_sse_url: str = os.getenv("TIMESFM_MCP_SSE_URL", "http://localhost:9003/sse")

    mcp_sse_read_timeout: int = int(os.getenv("MCP_SSE_READ_TIMEOUT", "300"))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "90"))
    api_key: str = os.getenv("API_KEY", "")
    netbox_url: str = os.getenv("NETBOX_URL", "http://localhost:8000")
    netbox_token: str = os.getenv("NETBOX_TOKEN", "")

    # TimesFM 远程推理(可选)
    timesfm_remote_url: str = os.getenv("TIMESFM_REMOTE_URL", "https://api-inference.huggingface.co/google/timesfm-1.0-200m-pytorch")
    timesfm_remote_token: str = os.getenv(
        "TIMESFM_REMOTE_TOKEN",
        os.getenv("HF_API_TOKEN", ""),
    )

    llm_strict: bool = os.getenv("LLM_STRICT", "false").lower() in {"1", "true", "yes", "on"}
    rag_mock_enabled: bool = os.getenv("RAG_MOCK_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    telemetry_mock_enabled: bool = os.getenv("TELEMETRY_MOCK_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    forecast_agent_enabled: bool = os.getenv("FORECAST_AGENT_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    forecast_interval_seconds: int = int(os.getenv("FORECAST_INTERVAL_SECONDS", "900"))
    disable_env_proxy: bool = os.getenv("DISABLE_ENV_PROXY", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

settings = Settings()
