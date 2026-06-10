import type { ReactNode } from 'react'

/** 轻量 Markdown 渲染（诊断报告用，无额外依赖） */

type Props = {
  text: string
  className?: string
}

function renderInline(text: string): ReactNode[] {
  const parts: ReactNode[] = []
  const re = /\*\*(.+?)\*\*/g
  let last = 0
  let m: RegExpExecArray | null
  let key = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      parts.push(text.slice(last, m.index))
    }
    parts.push(<strong key={key++}>{m[1]}</strong>)
    last = m.index + m[0].length
  }
  if (last < text.length) {
    parts.push(text.slice(last))
  }
  return parts.length ? parts : [text]
}

export default function MarkdownText({ text, className }: Props) {
  const lines = text.split('\n')
  const nodes: ReactNode[] = []
  let listItems: string[] = []
  let key = 0

  const flushList = () => {
    if (listItems.length === 0) {
      return
    }
    nodes.push(
      <ul key={key++} className="md-text__ul">
        {listItems.map((item, i) => (
          <li key={i}>{renderInline(item)}</li>
        ))}
      </ul>,
    )
    listItems = []
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    if (!line.trim()) {
      flushList()
      nodes.push(<div key={key++} className="md-text__gap" />)
      continue
    }
    if (line.startsWith('### ')) {
      flushList()
      nodes.push(
        <h4 key={key++} className="md-text__h4">
          {line.slice(4)}
        </h4>,
      )
      continue
    }
    if (line.startsWith('## ')) {
      flushList()
      nodes.push(
        <h3 key={key++} className="md-text__h3">
          {line.slice(3)}
        </h3>,
      )
      continue
    }
    if (line.startsWith('# ')) {
      flushList()
      nodes.push(
        <h2 key={key++} className="md-text__h2">
          {line.slice(2)}
        </h2>,
      )
      continue
    }
    if (/^[-*]\s+/.test(line)) {
      listItems.push(line.replace(/^[-*]\s+/, ''))
      continue
    }
    if (/^\d+\.\s+/.test(line)) {
      listItems.push(line.replace(/^\d+\.\s+/, ''))
      continue
    }
    flushList()
    nodes.push(
      <p key={key++} className="md-text__p">
        {renderInline(line)}
      </p>,
    )
  }
  flushList()

  return <div className={className ? `md-text ${className}` : 'md-text'}>{nodes}</div>
}
