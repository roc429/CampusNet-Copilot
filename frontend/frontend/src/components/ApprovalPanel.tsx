import type { ApprovalCommand } from '../api/agentApi'
import './ApprovalPanel.css'

type Props = {
  commands: ApprovalCommand[]
  busy?: boolean
  submitted?: 'approved' | 'rejected' | null
  error?: string | null
  onApprove: () => void
  onReject: () => void
}

export default function ApprovalPanel({
  commands,
  busy = false,
  submitted = null,
  error = null,
  onApprove,
  onReject,
}: Props) {
  if (submitted === 'approved') {
    return (
      <div className="approval-panel approval-panel--done">
        <p className="approval-panel__hint">已确认执行，后端正在继续 dry-run 并生成报告…</p>
      </div>
    )
  }

  if (submitted === 'rejected') {
    return (
      <div className="approval-panel approval-panel--done">
        <p className="approval-panel__hint">已拒绝自动修复，后端将跳过下发并生成诊断报告…</p>
      </div>
    )
  }

  return (
    <div className="approval-panel">
      <div className="approval-panel__header">
        <strong className="approval-panel__title">需要人工确认</strong>
        <span className="approval-panel__badge">RiskReview</span>
      </div>
      <p className="approval-panel__desc">
        以下控制命令被判定为中高风险。确认后将执行 mock SDN dry-run（不会真实改设备）；拒绝则跳过自动修复，仍生成诊断报告。
      </p>
      <ul className="approval-panel__commands">
        {commands.length === 0 ? (
          <li className="approval-panel__command">（后端未返回命令明细，仍可确认或拒绝以继续流程）</li>
        ) : (
          commands.map((cmd) => (
            <li key={cmd.command_id ?? `${cmd.target}-${cmd.command}`} className="approval-panel__command">
              <div className="approval-panel__command-text">{cmd.command ?? '未命名命令'}</div>
              {(cmd.target || cmd.risk_level) && (
                <div className="approval-panel__command-meta">
                  {cmd.target ? `目标：${cmd.target}` : null}
                  {cmd.target && cmd.risk_level ? ' · ' : null}
                  {cmd.risk_level ? `风险：${cmd.risk_level}` : null}
                </div>
              )}
              {cmd.rationale ? (
                <div className="approval-panel__command-rationale">{cmd.rationale}</div>
              ) : null}
            </li>
          ))
        )}
      </ul>
      {error ? <p className="approval-panel__error">{error}</p> : null}
      <div className="approval-panel__actions">
        <button
          type="button"
          className="approval-panel__btn approval-panel__btn--primary"
          disabled={busy}
          onClick={onApprove}
        >
          {busy ? '提交中…' : '确认执行并继续'}
        </button>
        <button
          type="button"
          className="approval-panel__btn approval-panel__btn--ghost"
          disabled={busy}
          onClick={onReject}
        >
          拒绝，仅生成报告
        </button>
      </div>
    </div>
  )
}
