"""智网学伴 MCP Servers 包。

按设计文档 §3.4 标准化工具总线层组织,各子包对应一个独立的 MCP Server:
- prometheus_mcp: Prometheus 指标查询(端口 9001)
- grafana_mcp:    Grafana 仪表盘检索(端口 9002)
- timesfm_mcp:    TimesFM 时序预测(端口 9003)
- campus_mcp:     校园业务工具占位(端口 9000,保持向后兼容)
"""
