# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CampusNet-Copilot (智网学伴)** — Agentic AI campus network intelligent operations system. Competition entry for "C4-2026". Submission deadline: **June 15, 2026**.

Pipeline: "302考场考试系统卡顿" → ChatAgent → RetrieverAgent (GraphRAG) → TelemetryAgent (Prometheus MCP) → PredictionAgent (TimesFM) → DiagnosisAgent (LLM) → StrategyAgent → RiskReview → Report.

**LLM**: Qwen3 via Alibaba DashScope. Two call sites:
- `frontend/backend/app/services/qwen_chat.py` — user-facing chat
- `net_infra/app/llm/client.py` — Agent reasoning (langchain_openai.ChatOpenAI, compatible mode)

## Architecture (branch: integration-merge — pushed to origin/main)

| Module | Author | Key entrypoint | Port |
|--------|--------|---------------|:---:|
| NMB/ | 赵中赐 | `NMB/topology_api.py` | 8001 |
| frontend/ | 马池美 | `frontend/backend/run.py` + `frontend/frontend/` | 8000, 3000 |
| mcp_servers/ | 刘兴 | 5 servers: campus/prometheus/grafana/timesfm/netbox | 9000-9003, 7001 |
| net_infra/ | 刘兴 | `net_infra/app/app.py` (Agent framework) | 8002 |
| external/ | 林嘉伟 | SDN Mininet + TimesFM engine | — |

## Server (Alibaba Cloud ECS)

- **IP**: 47.86.196.101 | **Password**: Jiawenpeng123
- **OS**: Ubuntu 22.04, 2C8G, Hong Kong
- **Conda**: `campusnet311` (Python 3.11)
- **Project**: `/root/CampusNet-Copilot`
- **Stop**: Console → Stop (普通停止), do NOT release public IP
- Full restart guide: `服务器恢复指南.md` (on Desktop)

## End-to-End Pipeline Status (2026-06-04 verified)

```
POST :8002/chat → ChatAgent → ✅
NetBox MCP (:7001) → ✅ (created mcp_servers/netbox_mcp/)
Prometheus MCP (:9001) → ✅ (real data via inject_prometheus_test_data.py)
LLM Diagnosis (Qwen3 via DashScope) → ✅
Remediation Plan → ✅
Security Review (SecurityGuardAgent) → ✅
Dry-run Execution → ✅
Diagnostic Report → ✅

TimesFM real model → ✅ (loaded via timesfm_src, TimesFM_2p5_200M_torch.from_pretrained)
TimesFM in MCP pipeline → ❌ (MCP uses EWMA fallback — needs to call real model)
RAG bridge in Agent tools → ❌ (endpoint exists but not in LangGraph tool chain)
Frontend real API → ❌ (Ma Chimei needs to switch from mock data)
```

## Key Modifications (serverside)

1. `mcp_servers/netbox_mcp/` — Created. Bridges NetBox REST API (:8000) to MCP protocol
2. `net_infra/app/rag_bridge.py` — Created. Agent ↝ NMB HTTP bridge
3. `net_infra/app/app.py` — Appended `/api/rag/test` endpoint
4. `external/neta/phase2/timesfm/timesfm_engine.py` — `_run_forecast` rewritten for TimesFM 2.x API
5. TimesFM installed from source: `pip install -e timesfm_src/` (from 林嘉伟's zip)
6. `huggingface_hub` upgraded to >=0.28.0 for TimesFM compatibility
7. Port conflicts resolved: Grafana 3000→3001, Milvus MinIO 9000→9010
8. `net_infra/.env` — LLM configured: BASE_URL=dashscope, MODEL=qwen-max, NETBOX_MCP_SSE_URL= (auto-starts own NetBox MCP)
9. `net_infra/docker-compose.yml` — Grafana port changed: "3001:3000"
10. `NMB/docker-compose.yml` — MinIO ports changed: "9010:9000", "9011:9001"

## Remaining Tasks (June 4-15)

| Priority | Task | Owner | Status |
|:---:|------|-------|:---:|
| 🔴 | TimesFM MCP call real model (not EWMA) | 贾文鹏 | ❌ |
| 🔴 | RAG bridge integrated into Agent tool chain | 贾文鹏 | ❌ |
| 🔴 | Frontend switch from mock to real API | 马池美 | ❌ |
| 🔴 | Design document (设计文档) | 贾文鹏 | ❌ |
| 🔴 | Demo video (5 min) | 马池美 | ❌ |
| 🟡 | device_id alignment (old → new) | 贾文鹏 | ❌ |
| 🟡 | TimesFM prediction curve frontend | 马池美 | ❌ |
| 🟡 | Experiment data from 赵中赐/刘兴/林嘉伟 | Team | ❌ |
| 🟢 | TimesFM model loading (local) | ✅ | — |
| 🟢 | End-to-end diagnosis pipeline | ✅ | — |
| 🟢 | Prometheus data injection | ✅ | — |
| 🟢 | 5 MCP servers all running | ✅ | — |
| 🟢 | Code pushed to GitHub (main) | ✅ | — |

## Common Pitfalls

- **Import errors**: Scripts must run from `~/CampusNet-Copilot` root, or use `PYTHONPATH=$(pwd)`
- **Conda after restart**: `eval "$(/root/miniconda3/bin/conda shell.bash hook)" && conda activate campusnet311`
- **Agent startup**: MUST be in `net_infra/` directory: `cd ~/CampusNet-Copilot/net_infra && nohup python3 -c "import uvicorn; uvicorn.run('app.app:app', ...)" > /tmp/agent_api.log 2>&1 &`
- **MCP startup**: From project root using `from mcp_servers.*.main import mcp, settings`
- **SSE can't be curl-tested**: Verify MCP via `ps aux | grep mcp_servers`
- **Workbench line truncation**: Use `nano` to write multi-line scripts, then `python3 script.py`
- **device_id mismatch**: Prometheus has old IDs (`AP-A3-2F-01`). Topology has new IDs (`AP-EXAM-302`).
- **NetBox MCP URL in .env**: Set to empty string — the Agent's StandardMCPManager auto-connects to the locally running NetBox MCP at :7001
