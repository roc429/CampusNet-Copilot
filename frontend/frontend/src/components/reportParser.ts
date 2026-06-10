export type ReportMeta = {
  eventId: string
  question: string
  status: string
  riskLevel: string
}

export type ReportSection = {
  id: string
  title: string
  body: string
  kind: 'conclusion' | 'plan' | 'commands' | 'security' | 'execution' | 'evidence' | 'actions' | 'info' | 'default'
}

export type ParsedReport = {
  meta: ReportMeta
  sections: ReportSection[]
}

const LABELED_SECTIONS: { key: string; title: string; kind: ReportSection['kind'] }[] = [
  { key: '诊断结论', title: '诊断结论', kind: 'conclusion' },
  { key: '诊断摘要', title: '诊断摘要', kind: 'conclusion' },
  { key: '修复计划', title: '修复计划', kind: 'plan' },
  { key: '可直接执行的控制命令', title: '可直接执行命令', kind: 'commands' },
  { key: '需要人工审批的控制命令', title: '需人工审批命令', kind: 'commands' },
  { key: '被阻断的控制命令', title: '被阻断命令', kind: 'security' },
  { key: '安全审查结果', title: '安全审查', kind: 'security' },
  { key: '执行结果', title: '执行结果', kind: 'execution' },
  { key: '验证结果', title: '验证结果', kind: 'execution' },
  { key: '调用链路', title: '调用链路', kind: 'info' },
  { key: '拓扑证据', title: '拓扑证据', kind: 'evidence' },
  { key: '指标证据', title: '指标证据', kind: 'evidence' },
  { key: '知识库证据', title: '知识库证据', kind: 'evidence' },
  { key: '可能原因', title: '可能原因', kind: 'conclusion' },
  { key: '建议操作', title: '建议操作', kind: 'actions' },
  { key: '缺失证据说明', title: '缺失证据', kind: 'info' },
  { key: '说明', title: '说明', kind: 'info' },
]

const META_KEYS = ['任务 ID', '任务ID', '用户问题', '最终状态', '风险等级'] as const

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function firstLine(block: string): string {
  const line = block.split('\n').find((l) => l.trim())?.trim() ?? ''
  return line.replace(/^\*\*(.+)\*\*$/, '$1').replace(/^[-*]\s+/, '')
}

function parseLabeledBlocks(text: string): Record<string, string> {
  const keys = [...META_KEYS, ...LABELED_SECTIONS.map((s) => s.key)]
  const uniqueKeys = [...new Set(keys)]
  const pattern = new RegExp(
    `(?:^|\\n\\n)(${uniqueKeys.map(escapeRe).join('|')})[：:]\\s*\\n([\\s\\S]*?)(?=\\n\\n(?:${uniqueKeys.map(escapeRe).join('|')})[：:]|$)`,
    'g',
  )
  const out: Record<string, string> = {}
  let m: RegExpExecArray | null
  while ((m = pattern.exec(text)) !== null) {
    out[m[1]] = m[2].trim()
  }
  return out
}

function metaFieldOnly(raw: string): string {
  if (!raw) {
    return ''
  }
  return firstLine(raw.split(/\n{2,}/)[0] ?? raw)
}

function tailAfterFirstParagraph(raw: string): string {
  if (!raw) {
    return ''
  }
  const idx = raw.search(/\n{2,}/)
  return idx >= 0 ? raw.slice(idx).trim() : ''
}

function normalizeRisk(raw: string): string {
  const line = metaFieldOnly(raw).toLowerCase()
  if (!line || line === '无。' || line === '无') {
    return '未标注'
  }
  if (/critical|严重|高/.test(line)) {
    return '高'
  }
  if (/warning|中等|中/.test(line)) {
    return '中等'
  }
  if (/info|低|轻微/.test(line)) {
    return '低'
  }
  if (raw.length <= 20 && !raw.includes('\n')) {
    return raw.trim()
  }
  return metaFieldOnly(raw) || '未标注'
}

function normalizeStatus(raw: string): string {
  const line = metaFieldOnly(raw)
  if (!line) {
    return '未知'
  }
  if (line.length <= 56) {
    return line
  }
  return `${line.slice(0, 53)}…`
}

function isEmptySection(body: string): boolean {
  const t = body.trim()
  return !t || t === '无。' || t === '无' || t === '暂无。'
}

function pushSection(
  sections: ReportSection[],
  seenTitles: Set<string>,
  section: ReportSection,
) {
  if (isEmptySection(section.body) || seenTitles.has(section.title)) {
    return
  }
  seenTitles.add(section.title)
  sections.push(section)
}

export function parseReportText(text: string, fallbackEventId: string, fallbackQuestion = ''): ParsedReport {
  const blocks = parseLabeledBlocks(text)

  const inlineEventId = text.match(/任务\s*ID[：:]\s*(\S+)/i)?.[1]
  const eventId =
    inlineEventId || firstLine(blocks['任务 ID'] ?? blocks['任务ID'] ?? '') || fallbackEventId
  const question = blocks['用户问题']?.trim() || fallbackQuestion
  const status = normalizeStatus(blocks['最终状态'] ?? '')

  const riskBlock = blocks['风险等级'] ?? ''
  const riskLevel = normalizeRisk(riskBlock)
  const riskOverflow = tailAfterFirstParagraph(riskBlock)

  const sections: ReportSection[] = []
  const seenTitles = new Set<string>()

  for (const def of LABELED_SECTIONS) {
    const body = blocks[def.key]
    if (!body || isEmptySection(body)) {
      continue
    }

    if (def.key === '风险等级') {
      continue
    }

    pushSection(sections, seenTitles, {
      id: def.key,
      title: def.title,
      body,
      kind: def.kind,
    })
  }

  if (riskOverflow && !blocks['诊断结论'] && !blocks['诊断摘要']) {
    pushSection(sections, seenTitles, {
      id: 'risk-tail-text',
      title: '诊断结论',
      body: riskOverflow,
      kind: 'conclusion',
    })
  }

  if (sections.length === 0 && text.trim()) {
    pushSection(sections, seenTitles, {
      id: 'raw',
      title: '报告全文',
      body: text.trim(),
      kind: 'default',
    })
  }

  return {
    meta: { eventId, question, status, riskLevel },
    sections,
  }
}

export function shortEventId(id: string): string {
  if (id.length <= 14) {
    return id
  }
  return `${id.slice(0, 10)}…${id.slice(-4)}`
}

export function riskTone(level: string): 'low' | 'medium' | 'high' | 'unknown' {
  const t = level.toLowerCase()
  if (/高|critical|严重/.test(t)) {
    return 'high'
  }
  if (/中|warning|中等/.test(t)) {
    return 'medium'
  }
  if (/低|info|轻微/.test(t)) {
    return 'low'
  }
  return 'unknown'
}

export function statusTone(status: string): 'ok' | 'warn' | 'unknown' {
  if (/完全解决|已解决|resolved|success/i.test(status)) {
    return 'ok'
  }
  if (/未完全|dry_run|人工|partial/i.test(status)) {
    return 'warn'
  }
  return 'unknown'
}

export function splitNumberedLines(body: string): string[] {
  const lines = body.split('\n').map((l) => l.trim()).filter(Boolean)
  const items: string[] = []
  for (const line of lines) {
    const m = line.match(/^\d+\.\s*(.+)/)
    if (m) {
      items.push(m[1])
    } else if (!line.startsWith('#')) {
      items.push(line)
    }
  }
  return items.length > 0 ? items : [body.trim()]
}

export function isListSection(kind: ReportSection['kind']): boolean {
  return kind === 'plan' || kind === 'commands' || kind === 'actions' || kind === 'execution'
}
