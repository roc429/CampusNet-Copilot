import type { AgentProgressItem, ApprovalCommand } from '../api/agentApi'
import { stageDisplay } from '../api/agentApi'

export type FlowCardStatus = 'pending' | 'running' | 'done' | 'warn'

export type FlowDetailLine = {
  stage: string
  label: string
  text: string
  done: boolean
}

export type AgentFlowCard = {
  id: string
  agentName: string
  accent: 'chat' | 'telemetry' | 'prediction' | 'diagnosis' | 'strategy' | 'risk' | 'report'
  action: string
  status: FlowCardStatus
  detailLines: FlowDetailLine[]
}

type FlowDef = {
  id: string
  agentName: string
  accent: AgentFlowCard['accent']
  defaultAction: string
  stages: string[]
}

const FLOW: FlowDef[] = [
  {
    id: 'chat',
    agentName: 'ChatAgent',
    accent: 'chat',
    defaultAction: '意图识别 → 故障诊断',
    stages: ['queued'],
  },
  {
    id: 'telemetry',
    agentName: 'TelemetryAgent',
    accent: 'telemetry',
    defaultAction: 'Prometheus 查询 → AP 指标采集',
    stages: [
      'diagnosis_started',
      'tool_prometheus_requested',
      'tool_prometheus_running',
      'tool_prometheus_completed',
      'tool_netbox_requested',
      'tool_netbox_running',
      'tool_netbox_completed',
    ],
  },
  {
    id: 'prediction',
    agentName: 'PredictionAgent',
    accent: 'prediction',
    defaultAction: 'TimesFM 预测 → 未来趋势分析',
    stages: [
      'tool_timesfm_requested',
      'tool_timesfm_running',
      'tool_timesfm_completed',
    ],
  },
  {
    id: 'diagnosis',
    agentName: 'DiagnosisAgent',
    accent: 'diagnosis',
    defaultAction: 'LLM 推理 → 根因分析',
    stages: ['llm_reasoning', 'llm_finalizing'],
  },
  {
    id: 'strategy',
    agentName: 'StrategyAgent',
    accent: 'strategy',
    defaultAction: '生成修复策略',
    stages: ['workflow_ingest', 'remediation_planning', 'security_review'],
  },
  {
    id: 'risk',
    agentName: 'RiskReview',
    accent: 'risk',
    defaultAction: '安全审计 → 人工确认',
    stages: [
      'waiting_approval',
      'approval_received',
      'approval_rejected',
      'approval_skipped',
      'sdn_compile',
      'sdn_dispatch',
      'merge',
      'verification',
      'escalate',
    ],
  },
  {
    id: 'report',
    agentName: '报告生成',
    accent: 'report',
    defaultAction: '汇总诊断与闭环结果',
    stages: ['completed'],
  },
]

function itemsForCard(progress: AgentProgressItem[], stages: string[]): AgentProgressItem[] {
  const stageSet = new Set(stages)
  return progress.filter((p) => stageSet.has(p.stage))
}

function summarizeAction(card: FlowDef, items: AgentProgressItem[], approvalCount: number): string {
  if (card.id === 'risk' && approvalCount > 0) {
    return `${approvalCount} 条命令需人工确认`
  }

  const last = items[items.length - 1]
  if (!last?.message) {
    return card.defaultAction
  }

  const msg = last.message
  if (card.id === 'telemetry') {
    const toolMatch = msg.match(/(get_device_metrics|instant_query|range_query)/i)
    const deviceMatch = msg.match(/device_ids?["\s:]*\[([^\]]+)\]/i)
    const parts: string[] = []
    if (toolMatch) {
      parts.push(`工具：${toolMatch[1]}`)
    }
    if (deviceMatch) {
      parts.push(`设备：${deviceMatch[1].replace(/"/g, '').trim()}`)
    }
    if (parts.length > 0) {
      return `Prometheus 查询 → ${parts.join(' · ')}`
    }
  }

  if (card.id === 'prediction') {
    const toolMatch = msg.match(
      /(forecast_metric|forecast_quantile|detect_anomaly_window)/i,
    )
    const horizonMatch = msg.match(/horizon_minutes["\s:]*(\d+)/i)
    const metricMatch = msg.match(/metric["\s:]*"?([\w_]+)"?/i)
    const parts: string[] = []
    if (toolMatch) {
      parts.push(`工具：${toolMatch[1]}`)
    }
    if (metricMatch) {
      parts.push(`指标：${metricMatch[1]}`)
    }
    if (horizonMatch) {
      parts.push(`窗口：${horizonMatch[1]}min`)
    }
    if (parts.length > 0) {
      return `TimesFM 预测 → ${parts.join(' · ')}`
    }
    return 'TimesFM 预测 → 未来趋势分析'
  }

  if (card.id === 'diagnosis' && /推理|结论/.test(msg)) {
    return 'LLM 推理 → 根因分析'
  }

  if (card.id === 'strategy' && /修复|策略|审查/.test(msg)) {
    return '生成修复策略与安全审查'
  }

  if (card.id === 'report' || last.stage === 'completed') {
    return '诊断报告已生成'
  }

  return card.defaultAction
}

function isProgressItemDone(
  item: AgentProgressItem,
  index: number,
  total: number,
  cardStatus: FlowCardStatus,
): boolean {
  if (item.status === 'completed') {
    return true
  }
  if (item.status === 'failed') {
    return false
  }
  if (item.stage.endsWith('_completed') || item.stage === 'completed') {
    return true
  }
  if (index < total - 1) {
    return true
  }
  return cardStatus === 'done'
}

function buildDetailLines(
  card: FlowDef,
  items: AgentProgressItem[],
  commands: ApprovalCommand[],
  cardStatus: FlowCardStatus,
): FlowDetailLine[] {
  const lines: FlowDetailLine[] = items
    .map((item, index) => {
      const text = item.message?.trim()
      if (!text) {
        return null
      }
      const display = stageDisplay(item.stage, item.message)
      return {
        stage: item.stage,
        label: display.label,
        text,
        done: isProgressItemDone(item, index, items.length, cardStatus),
      }
    })
    .filter((line): line is FlowDetailLine => line !== null)

  if (card.id === 'risk' && commands.length > 0) {
    for (const cmd of commands) {
      lines.push({
        stage: 'approval_cmd',
        label: '待审批命令',
        text: [
          cmd.command_type ? `类型：${cmd.command_type}` : null,
          cmd.target ? `目标：${cmd.target}` : null,
          cmd.command ? `命令：${cmd.command}` : null,
          cmd.risk_level ? `风险：${cmd.risk_level}` : null,
        ]
          .filter(Boolean)
          .join(' · '),
        done: cardStatus === 'done',
      })
    }
  }

  const seen = new Set<string>()
  return lines.filter((line) => {
    const key = `${line.stage}:${line.text}`
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

export function buildAgentFlowCards(
  progress: AgentProgressItem[],
  opts: {
    reportReady?: boolean
    approvalRequired?: boolean
    approvalCommands?: ApprovalCommand[]
  } = {},
): AgentFlowCard[] {
  const { reportReady = false, approvalRequired = false, approvalCommands = [] } = opts
  const lastStage = progress[progress.length - 1]?.stage
  let activeIndex = 0

  if (lastStage) {
    const idx = FLOW.findIndex((card) => card.stages.includes(lastStage))
    if (idx >= 0) {
      activeIndex = idx
    }
  }
  if (reportReady) {
    activeIndex = FLOW.length - 1
  }

  return FLOW.map((card, index) => {
    const items = itemsForCard(progress, card.stages)
    const hasItems = items.length > 0

    let status: FlowCardStatus = 'pending'
    if (reportReady || index < activeIndex) {
      status = 'done'
    } else if (index === activeIndex) {
      if (card.id === 'risk' && (approvalRequired || lastStage === 'waiting_approval')) {
        status = 'warn'
      } else if (hasItems || reportReady) {
        status = lastStage === 'completed' ? 'done' : 'running'
      }
    }

    if (card.id === 'report' && reportReady) {
      status = 'done'
    }

    // 非预测类问题未调用 TimesFM 时，流水线已过该步则标记为跳过
    let action = summarizeAction(card, items, approvalCommands.length)
    if (card.id === 'prediction' && !hasItems && index < activeIndex) {
      status = 'done'
      action = '未触发时序预测（跳过）'
    }

    return {
      id: card.id,
      agentName: card.agentName,
      accent: card.accent,
      action,
      status,
      detailLines: buildDetailLines(card, items, approvalCommands, status),
    }
  })
}

export function diagnosisIntroText(eventId?: string): string {
  if (!eventId) {
    return '诊断任务创建失败，请稍后重试。'
  }
  return '已收到你的问题，Agent 流水线正在执行诊断。'
}
