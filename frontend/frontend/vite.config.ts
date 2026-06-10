import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const remoteHost = env.VITE_REMOTE_HOST || 'http://47.86.196.101'

  const agentTarget = env.VITE_AGENT_PROXY_TARGET || `${remoteHost}:8002`
  const ragTarget = env.VITE_RAG_PROXY_TARGET || agentTarget
  const mcpTarget = env.VITE_MCP_PROXY_TARGET || agentTarget
  const opsTarget = env.VITE_OPS_PROXY_TARGET || agentTarget
  const backendTarget = env.VITE_BACKEND_PROXY_TARGET || `${remoteHost}:8000`
  const monitorTarget = env.VITE_MONITOR_PROXY_TARGET || backendTarget
  const adminTarget = env.VITE_ADMIN_PROXY_TARGET || agentTarget
  const ecsAgentTarget = env.VITE_ECS_AGENT_PROXY_TARGET || adminTarget
  const nmbTarget = env.VITE_NMB_PROXY_TARGET || `${remoteHost}:8001`

  return {
    plugins: [react()],
    server: {
      proxy: {
        // Agent 引擎 (:8002) — 路径越具体越靠前
        '/api/agent': { target: agentTarget, changeOrigin: true },
        // 2.4 GraphRAG 检索 — 可单独指向 ECS（VITE_RAG_PROXY_TARGET）
        '/api/rag': { target: ragTarget, changeOrigin: true },
        // 2.7 预测 / TimesFM — 可单独指向 ECS（VITE_OPS_PROXY_TARGET / VITE_MCP_PROXY_TARGET）
        '/api/ops': { target: opsTarget, changeOrigin: true },
        '/api/mcp': { target: mcpTarget, changeOrigin: true },
        '/chat': { target: agentTarget, changeOrigin: true },
        '/tasks': { target: agentTarget, changeOrigin: true },
        '/reports': { target: agentTarget, changeOrigin: true },
        // 报告中心读 ECS 历史（/admin/events、/reports 等，不影响本机 /chat 诊断）
        '/ecs-agent': {
          target: ecsAgentTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/ecs-agent/, ''),
        },
        '/admin': { target: adminTarget, changeOrigin: true },
        // NMB 拓扑 (:8001)，与文档 2.5 一致
        '/api/v1': { target: nmbTarget, changeOrigin: true },
        // 知识库拓扑：当前前端走 /api/knowledge/topology（frontend backend :8000）
        '/api/knowledge': { target: backendTarget, changeOrigin: true },
        // 监控 KPI — 可单独指向 ECS（VITE_MONITOR_PROXY_TARGET）
        '/api/monitor': { target: monitorTarget, changeOrigin: true },
        // 登录、百炼聊天等其余 /api → frontend backend (:8000)
        '/api': { target: backendTarget, changeOrigin: true },
      },
    },
  }
})
