import { useState } from 'react'
import {
  Check,
  CheckCircle2,
  ChevronRight,
  Copy,
  LayoutList,
  Shield,
} from 'lucide-react'
import MarkdownText from './MarkdownText'
import {
  isListSection,
  parseReportText,
  riskTone,
  shortEventId,
  splitNumberedLines,
  statusTone,
  type ReportSection,
} from './reportParser'
import './DiagnosisReportCard.css'

type Props = {
  eventId: string
  reportText: string
  question?: string
  variant?: 'inline' | 'center'
}

const SECTION_ICON: Record<ReportSection['kind'], string> = {
  conclusion: '◆',
  plan: '▣',
  commands: '⌘',
  security: '⚠',
  execution: '→',
  evidence: '◎',
  actions: '✦',
  info: 'i',
  default: '•',
}

function SectionBlock({ section, variant }: { section: ReportSection; variant: 'inline' | 'center' }) {
  const useList = isListSection(section.kind) && /^\d+\./m.test(section.body)
  const items = useList ? splitNumberedLines(section.body) : []

  return (
    <section className={`diag-report__section diag-report__section--${section.kind}`}>
      <h3 className="diag-report__section-title">
        <span className="diag-report__section-icon" aria-hidden="true">
          {variant === 'center' && section.kind === 'conclusion' ? (
            <LayoutList size={14} strokeWidth={2.25} />
          ) : (
            SECTION_ICON[section.kind]
          )}
        </span>
        <span className="diag-report__section-title-text">{section.title}</span>
      </h3>
      <div className="diag-report__section-body">
        {useList && items.length > 1 ? (
          <ol className="diag-report__list">
            {items.map((item, i) => (
              <li key={i} className="diag-report__list-item">
                {item.includes(' -- ') || item.includes('；') ? (
                  <span className="diag-report__cmd">{item}</span>
                ) : (
                  item
                )}
              </li>
            ))}
          </ol>
        ) : section.kind === 'info' && section.title === '说明' ? (
          <p className="diag-report__footnote">{section.body}</p>
        ) : (
          <MarkdownText text={section.body} className="diag-report__md" />
        )}
      </div>
    </section>
  )
}

export default function DiagnosisReportCard({
  eventId,
  reportText,
  question = '',
  variant = 'inline',
}: Props) {
  const [copied, setCopied] = useState(false)
  const parsed = parseReportText(reportText, eventId, question)
  const { meta, sections } = parsed
  const risk = riskTone(meta.riskLevel)
  const status = statusTone(meta.status)
  const isCenter = variant === 'center'

  const mainSections = sections.filter((s) => s.title !== '说明')
  const footnote = sections.find((s) => s.title === '说明')

  async function handleCopyId() {
    try {
      await navigator.clipboard.writeText(meta.eventId)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }

  return (
    <article className={`diag-report diag-report--${variant}`}>
      <header className="diag-report__hero">
        {isCenter ? (
          <div className="diag-report__hero-top">
            <span className="diag-report__crumb">
              <ChevronRight size={16} className="diag-report__crumb-icon" aria-hidden="true" />
              诊断报告
            </span>
            <span className="diag-report__id-row">
              <code className="diag-report__id" title={meta.eventId}>
                {shortEventId(meta.eventId)}
              </code>
              <button
                type="button"
                className={copied ? 'diag-report__copy diag-report__copy--done' : 'diag-report__copy'}
                title={copied ? '已复制' : '复制 ID'}
                aria-label={copied ? '已复制' : '复制 ID'}
                onClick={() => void handleCopyId()}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
              </button>
            </span>
          </div>
        ) : (
          <div className="diag-report__hero-top">
            <span className="diag-report__badge">诊断报告</span>
            <code className="diag-report__id" title={meta.eventId}>
              {shortEventId(meta.eventId)}
            </code>
          </div>
        )}
        {meta.question ? <p className="diag-report__question">{meta.question}</p> : null}
        <div className="diag-report__metrics">
          <div className={`diag-report__metric diag-report__metric--status-${status}`}>
            {isCenter ? (
              <span className="diag-report__metric-icon" aria-hidden="true">
                <CheckCircle2 size={20} strokeWidth={2} />
              </span>
            ) : null}
            <div className="diag-report__metric-text">
              <span className="diag-report__metric-label">最终状态</span>
              <span className="diag-report__metric-value" title={meta.status}>
                {meta.status || '—'}
              </span>
            </div>
          </div>
          <div className={`diag-report__metric diag-report__metric--risk-${risk}`}>
            {isCenter ? (
              <span className="diag-report__metric-icon" aria-hidden="true">
                <Shield size={20} strokeWidth={2} />
              </span>
            ) : null}
            <div className="diag-report__metric-text">
              <span className="diag-report__metric-label">风险等级</span>
              <span className="diag-report__metric-value">{meta.riskLevel || '—'}</span>
            </div>
          </div>
        </div>
      </header>

      <div className="diag-report__content">
        {mainSections.map((section) => (
          <SectionBlock key={section.id} section={section} variant={variant} />
        ))}
        {footnote ? <SectionBlock section={footnote} variant={variant} /> : null}
      </div>
    </article>
  )
}
