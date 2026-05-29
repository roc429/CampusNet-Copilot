"""MCP Server日志格式。"""

from __future__ import annotations

import logging


def configure_logging(server_name: str, level: int = logging.INFO) -> logging.Logger:
    """统一所有 MCP Server 的日志格式,便于审计与调用链追踪。

    Args:
        server_name: 服务名,会作为 logger 名出现在日志前缀中。
        level: 日志级别,默认 INFO。

    Returns:
        与 server_name 同名的 logger 实例,可直接使用。
    """

    logging.basicConfig(
        level=level,
        format=f"%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=False,
    )
    logger = logging.getLogger(server_name)
    logger.setLevel(level)
    return logger
