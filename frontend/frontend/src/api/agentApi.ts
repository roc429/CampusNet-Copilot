/** Agent 引擎 (:8002) API — 开发环境经 Vite 代理，生产可设 VITE_AGENT_BASE_URL */

const agentBase = import.meta.env.VITE_AGENT_BASE_URL ?? ''
/** 报告中心读 ECS 历史（开发环境经 Vite /ecs-agent 代理） */
const ecsAgentBase = import.meta.env.VITE_ECS_AGENT_BASE_URL ?? '/ecs-agent'

export type AgentProgressItem = {
  stage: string
  message: string
  status?: string
}

export type ApprovalCommand = {
  command_id?: string
  command_type?: string
  target?: string
  command?: string
  risk_level?: string
  requires_approval?: boolean
  dry_run?: boolean
  rationale?: string
}

export type AgentStatusResponse = {
  latest_event_id?: string | null
  event_id?: string | null
  status?: string
  current_stage?: string | null
  progress?: AgentProgressItem[]
  report_ready?: boolean
  report_text?: string | null
  approval_required?: boolean
  approval_commands?: ApprovalCommand[]
}

export type McpServerHealth = {
  server_name: string
  connected: boolean
  tool_count?: number
  tools?: string[]
  endpoint?: string
  transport?: string
}

export type McpHealthResponse = {
  ok: boolean
  error?: string
  servers?: McpServerHealth[]
}

export type RagTopologyEdge = {
  source: string
  relation: string
  target: string
}

export type RagTestResponse = {
  ok: boolean
  evidence_snapshot?: string
  topology_chain?: RagTopologyEdge[]
  semantic_hits?: string[]
  source?: string
  detail?: string
  error?: string
}

export type ReportResponse = {
  event_id: string
  report_text: string
}

export type AdminEvent = {
  event_id: string
  event_type?: string
  source?: string
  user_id?: string | null
  question?: string | null
  device_id?: string | null
  severity?: string
  status?: string
  timestamp?: string
}

export function extractEventId(text: string): string | null {
  const m = text.match(/evt-[a-f0-9]+/i)
  return m ? m[0] : null
}

export async function postChat(userId: string, question: string): Promise<{ answer: string }> {
  const res = await fetch(`${agentBase}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, question }),
  })
  const body = (await res.json().catch(() => ({}))) as { answer?: string; detail?: string }
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `诊断请求失败 (${res.status})`)
  }
  if (!body.answer) {
    throw new Error('Agent 未返回回答')
  }
  return { answer: body.answer }
}

export async function fetchAgentStatus(eventId: string): Promise<AgentStatusResponse> {
  const res = await fetch(
    `${agentBase}/api/agent/status?${new URLSearchParams({ event_id: eventId })}`,
  )
  const body = (await res.json().catch(() => ({}))) as AgentStatusResponse & { detail?: string }
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `状态查询失败 (${res.status})`)
  }
  return body
}

export async function postTaskApprove(eventId: string, approvedBy: string): Promise<{ status: string }> {
  const res = await fetch(`${agentBase}/tasks/${encodeURIComponent(eventId)}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved_by: approvedBy }),
  })
  const body = (await res.json().catch(() => ({}))) as { status?: string; detail?: string }
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `审批确认失败 (${res.status})`)
  }
  return { status: body.status ?? 'approved' }
}

export async function postTaskReject(eventId: string, rejectedBy: string): Promise<{ status: string }> {
  const res = await fetch(`${agentBase}/tasks/${encodeURIComponent(eventId)}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved_by: rejectedBy, rejected_by: rejectedBy }),
  })
  const body = (await res.json().catch(() => ({}))) as { status?: string; detail?: string }
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `审批拒绝失败 (${res.status})`)
  }
  return { status: body.status ?? 'rejected' }
}

export async function fetchReport(eventId: string): Promise<ReportResponse> {
  const res = await fetch(`${agentBase}/reports/${encodeURIComponent(eventId)}`)
  const body = (await res.json().catch(() => ({}))) as ReportResponse & { detail?: string }
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `报告获取失败 (${res.status})`)
  }
  return body
}

/** 报告中心 — GET /admin/events（ECS Agent） */
export async function fetchAdminEvents(): Promise<AdminEvent[]> {
  const res = await fetch(`${ecsAgentBase}/admin/events`)
  const body = (await res.json().catch(() => null)) as AdminEvent[] | { detail?: string } | null
  if (!res.ok) {
    const detail = body && !Array.isArray(body) && typeof body.detail === 'string' ? body.detail : null
    throw new Error(detail ?? `事件列表获取失败 (${res.status})`)
  }
  return Array.isArray(body) ? body : []
}

/** 报告中心 — GET /reports/{event_id}（ECS Agent） */
export async function fetchRemoteReport(eventId: string): Promise<ReportResponse> {
  const res = await fetch(`${ecsAgentBase}/reports/${encodeURIComponent(eventId)}`)
  const body = (await res.json().catch(() => ({}))) as ReportResponse & { detail?: string }
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `报告获取失败 (${res.status})`)
  }
  return body
}

/** 报告中心 — GET /api/agent/status（ECS Agent，查报告是否就绪） */
export async function fetchRemoteAgentStatus(eventId: string): Promise<AgentStatusResponse> {
  const res = await fetch(
    `${ecsAgentBase}/api/agent/status?${new URLSearchParams({ event_id: eventId })}`,
  )
  const body = (await res.json().catch(() => ({}))) as AgentStatusResponse & { detail?: string }
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `状态查询失败 (${res.status})`)
  }
  return body
}

export async function fetchMcpHealth(): Promise<McpHealthResponse> {
  const res = await fetch(`${agentBase}/api/mcp/health`)
  return (await res.json().catch(() => ({ ok: false, error: '响应解析失败' }))) as McpHealthResponse
}

export async function callMcpTool(
  serverName: string,
  toolName: string,
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const res = await fetch(`${agentBase}/api/mcp/call`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ server_name: serverName, tool_name: toolName, arguments: args }),
  })
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown> & { detail?: string }
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `MCP 调用失败 (${res.status})`)
  }
  return body
}

/** 从 /api/mcp/call 响应中取出 structured_content（兼容顶层字段） */
export function extractMcpStructured(payload: Record<string, unknown>): Record<string, unknown> {
  const structured = payload.structured_content
  if (structured && typeof structured === 'object' && !Array.isArray(structured)) {
    return structured as Record<string, unknown>
  }
  return payload
}

/** 2.4 知识库检索 — GET /api/rag/test（开发环境经 Vite 代理到 Agent :8002） */
export async function fetchRagTest(deviceId: string, query: string): Promise<RagTestResponse> {
  const params = new URLSearchParams({ device_id: deviceId, query })
  const res = await fetch(`${agentBase}/api/rag/test?${params}`)
  const body = (await res.json().catch(() => ({}))) as RagTestResponse & { detail?: string }
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `RAG 检索失败 (${res.status})`)
  }
  if (!body.ok) {
    throw new Error(body.error || body.detail || 'RAG 检索失败')
  }
  return body
}

/** stage → 前端展示标签 */
export const STAGE_LABELS: Record<string, { label: string; tone: 'idle' | 'running' | 'done' | 'warn' | 'error' }> = {
  queued: { label: 'ChatAgent：任务已排队', tone: 'idle' },
  diagnosis_started: { label: 'TelemetryAgent：开始采集指标', tone: 'running' },
  tool_prometheus_requested: { label: 'TelemetryAgent：请求 Prometheus 指标', tone: 'running' },
  tool_prometheus_running: { label: 'TelemetryAgent：分析 Prometheus 指标', tone: 'running' },
  tool_prometheus_completed: { label: 'TelemetryAgent：指标查询完成', tone: 'done' },
  tool_netbox_requested: { label: 'RetrieverAgent：查询设备拓扑', tone: 'running' },
  tool_netbox_running: { label: 'RetrieverAgent：拓扑查询中', tone: 'running' },
  tool_netbox_completed: { label: 'RetrieverAgent：拓扑查询完成', tone: 'done' },
  tool_timesfm_requested: { label: 'PredictionAgent：时序预测', tone: 'running' },
  tool_timesfm_running: { label: 'PredictionAgent：预测分析中', tone: 'running' },
  tool_timesfm_completed: { label: 'PredictionAgent：预测完成', tone: 'done' },
  llm_reasoning: { label: 'DiagnosisAgent：模型推理中', tone: 'running' },
  llm_finalizing: { label: 'DiagnosisAgent：生成诊断结论', tone: 'running' },
  remediation_planning: { label: 'StrategyAgent：生成修复策略', tone: 'running' },
  security_review: { label: 'RiskReview：安全审计中', tone: 'warn' },
  waiting_approval: { label: '等待人工审批', tone: 'warn' },
  approval_received: { label: '已确认，继续执行', tone: 'done' },
  approval_rejected: { label: '已拒绝自动修复', tone: 'warn' },
  approval_skipped: { label: '无需审批', tone: 'done' },
  sdn_compile: { label: 'SDN：编译控制命令', tone: 'running' },
  sdn_dispatch: { label: 'SDN：dry-run 执行', tone: 'running' },
  completed: { label: '诊断报告已生成', tone: 'done' },
}

export function stageDisplay(stage: string, fallbackMessage?: string) {
  const mapped = STAGE_LABELS[stage]
  if (mapped) {
    return mapped
  }
  return {
    label: fallbackMessage?.trim() || stage,
    tone: 'running' as const,
  }
}
