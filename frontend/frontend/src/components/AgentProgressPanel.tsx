import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { ApprovalCommand } from '../api/agentApi'
import type { AgentProgressItem } from '../api/agentApi'
import { buildAgentFlowCards } from './agentFlowCards'
import './AgentProgressPanel.css'

type Props = {
  progress: AgentProgressItem[]
  status?: string
  reportReady?: boolean
  approvalRequired?: boolean
  approvalCommands?: ApprovalCommand[]
  approvalBusy?: boolean
  approvalSubmitted?: 'approved' | 'rejected' | null
  approvalError?: string | null
  onApprove?: () => void
  onReject?: () => void
}

const STATUS_LABEL = {
  pending: '等待中',
  running: '执行中',
  done: '已完成',
  warn: '待审批',
} as const

export default function AgentProgressPanel({
  progress,
  status,
  reportReady,
  approvalRequired = false,
  approvalCommands = [],
  approvalBusy = false,
  approvalSubmitted = null,
  approvalError = null,
  onApprove,
  onReject,
}: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  if (progress.length === 0 && !reportReady) {
    return (
      <div className="agent-think agent-think--empty">
        <span className="agent-think__pulse" aria-hidden="true" />
        等待 Agent 流水线响应…
      </div>
    )
  }

  const cards = buildAgentFlowCards(progress, {
    reportReady,
    approvalRequired: approvalRequired && !approvalSubmitted,
    approvalCommands,
  }).filter((card) => card.status !== 'pending')

  const headerStatus = reportReady
    ? '已完成'
    : status === 'waiting_approval'
      ? '等待审批'
      : '运行中'

  const showApproval =
    approvalRequired && !approvalSubmitted && !reportReady && onApprove && onReject

  function toggleCard(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  return (
    <div className="agent-think" role="log" aria-live="polite">
      <div className="agent-think__header">
        <span className="agent-think__title">代理思考流</span>
        <span
          className={`agent-think__badge agent-think__badge--${reportReady ? 'done' : status === 'waiting_approval' ? 'warn' : 'run'}`}
        >
          {headerStatus}
        </span>
      </div>

      <div className="agent-think__list">
        {cards.map((card) => {
          const isOpen = expanded[card.id] ?? false
          const hasSteps = card.detailLines.length > 0
          const hasApproval = card.id === 'risk' && showApproval
          const canExpand = hasSteps || hasApproval

          return (
            <div
              key={card.id}
              className={`agent-think__card agent-think__card--${card.accent} agent-think__card--${card.status} ${isOpen ? 'agent-think__card--open' : ''}`}
            >
              <button
                type="button"
                className="agent-think__card-head"
                onClick={() => canExpand && toggleCard(card.id)}
                disabled={!canExpand}
                aria-expanded={canExpand ? isOpen : undefined}
              >
                <span
                  className={`agent-think__dot agent-think__dot--${card.accent} ${card.status === 'running' ? 'agent-think__dot--pulse' : ''}`}
                  aria-hidden="true"
                />
                <span className="agent-think__card-main">
                  <span className="agent-think__card-title-row">
                    <span className="agent-think__card-title">{card.agentName}</span>
                    <span className={`agent-think__card-status agent-think__card-status--${card.status}`}>
                      {STATUS_LABEL[card.status]}
                    </span>
                  </span>
                  <span className="agent-think__card-brief">{card.action}</span>
                </span>
                {canExpand ? (
                  <ChevronDown
                    size={16}
                    className={`agent-think__chevron ${isOpen ? 'agent-think__chevron--open' : ''}`}
                    aria-hidden="true"
                  />
                ) : null}
              </button>

              {canExpand && isOpen ? (
                <div className="agent-think__card-body">
                  {card.detailLines.map((line, idx) => (
                    <div key={`${line.stage}-${idx}`} className="agent-think__step">
                      <span
                        className={`agent-think__step-check ${line.done ? 'agent-think__step-check--done' : 'agent-think__step-check--pending'}`}
                        aria-hidden="true"
                      >
                        {line.done ? '✓' : ''}
                      </span>
                      <div className="agent-think__step-content">
                        <div className="agent-think__step-label">{line.label}</div>
                        <p className="agent-think__step-text">{line.text}</p>
                      </div>
                    </div>
                  ))}

                  {hasApproval ? (
                    <div className="agent-think__approval">
                      {approvalError ? <p className="agent-think__approval-err">{approvalError}</p> : null}
                      <div className="agent-think__approval-actions">
                        <button
                          type="button"
                          className="agent-think__btn agent-think__btn--approve"
                          disabled={approvalBusy}
                          onClick={onApprove}
                        >
                          {approvalBusy ? '提交中…' : '批准'}
                        </button>
                        <button
                          type="button"
                          className="agent-think__btn agent-think__btn--reject"
                          disabled={approvalBusy}
                          onClick={onReject}
                        >
                          拒绝
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          )
        })}

        {approvalSubmitted === 'approved' ? (
          <p className="agent-think__hint">已批准，正在继续 dry-run 并生成报告…</p>
        ) : null}
        {approvalSubmitted === 'rejected' ? (
          <p className="agent-think__hint">已拒绝自动修复，正在生成诊断报告…</p>
        ) : null}
      </div>
    </div>
  )
}
