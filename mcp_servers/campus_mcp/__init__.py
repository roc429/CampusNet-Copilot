"""Campus MCP Server 包。

按设计文档 §3.4.1,Campus MCP 承担"工单衔接、仿真环境联动、知识库检索"
等校园专有业务。本次拆分先把 Prometheus / Grafana 工具迁出,
此处保留入口与 ping 工具占位,后续迭代加入工单与 SDN 沙盒工具。
"""
