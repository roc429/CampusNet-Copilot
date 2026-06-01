import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import KnowledgeGraphChart, { type KnowledgeGraphChartHandle } from './KnowledgeGraphChart.tsx'
import './KnowledgePanel.css'
import {
  Bookmark,
  CheckCircle2,
  Copy,
  Download,
  Maximize2,
  MoreHorizontal,
  MousePointer2,
  Network,
  Play,
  RefreshCw,
  Search,
  X,
} from 'lucide-react'

export type TopologyNode = {
  id: string
  label: string
  type: string
  properties: Record<string, unknown>
}

export type TopologyEdge = {
  id: string
  source: string
  target: string
  relation: string
  properties?: Record<string, unknown>
}

export type TopologyMeta = {
  node_labels: string[]
  relationship_types: string[]
  node_counts: Record<string, number>
  relationship_counts: Record<string, number>
  total_nodes: number
  total_edges: number
}

export type TopologyResponse = {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
  meta?: TopologyMeta
  raw?: {
    cypher: { topology: string; import_example: string[] }
    records: unknown[]
  }
}

type DataSource = 'live' | 'mock'
type ViewMode = 'graph' | 'table' | 'raw'

const MOCK_TOPOLOGY: TopologyResponse = {
  nodes: [
    {
      id: 'AP-EXAM-302',
      label: '302考场AP',
      type: 'Device',
      properties: { deviceID: 'AP-EXAM-302', name: '302考场AP', _neo4j_id: 0 },
    },
    {
      id: 'SW-EXAM-3F',
      label: '考试楼三层接入交换机',
      type: 'Switch',
      properties: { deviceID: 'SW-EXAM-3F', name: '考试楼三层接入交换机', _neo4j_id: 1 },
    },
    {
      id: 'AREA-302',
      label: '302考场',
      type: 'Area',
      properties: { name: '302考场', _neo4j_id: 2 },
    },
  ],
  edges: [
    {
      id: 'e1',
      source: 'AP-EXAM-302',
      target: 'SW-EXAM-3F',
      relation: 'CONNECTED_TO',
      properties: {},
    },
    {
      id: 'e2',
      source: 'AP-EXAM-302',
      target: 'AREA-302',
      relation: 'LOCATED_IN',
      properties: {},
    },
  ],
  meta: {
    node_labels: ['Area', 'Device', 'Switch'],
    relationship_types: ['CONNECTED_TO', 'LOCATED_IN'],
    node_counts: { Area: 1, Device: 1, Switch: 1 },
    relationship_counts: { CONNECTED_TO: 1, LOCATED_IN: 1 },
    total_nodes: 3,
    total_edges: 2,
  },
  raw: {
    cypher: {
      topology: 'MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 200',
      import_example: [
        'MERGE (ap:Device {deviceID: "AP-EXAM-302", name: "302考场AP"})',
        'MERGE (sw:Switch {deviceID: "SW-EXAM-3F", name: "考试楼三层接入交换机"})',
        'MERGE (area:Area {name: "302考场"})',
        'MERGE (ap)-[:CONNECTED_TO]->(sw)',
        'MERGE (ap)-[:LOCATED_IN]->(area)',
      ],
    },
    records: [],
  },
}

const DISPLAY_CYPHER = 'MATCH (n) RETURN n LIMIT 25;'

function collectPropertyKeys(nodes: TopologyNode[]): string[] {
  const keys = new Set<string>()
  for (const node of nodes) {
    for (const key of Object.keys(node.properties)) {
      if (!key.startsWith('_')) keys.add(key)
    }
  }
  return Array.from(keys).sort()
}

function pillVariant(label: string): 'area' | 'device' | 'switch' | 'all' {
  const key = label.toLowerCase()
  if (key === 'area' || key === 'device' || key === 'switch') return key
  return 'all'
}

function formatElapsed(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function copyText(text: string) {
  void navigator.clipboard?.writeText(text)
}

/** oneLight 主题：去掉 token 背景，代码直接铺在结果区渐变底上 */
const jsonCodeStyle = Object.fromEntries(
  Object.entries(oneLight).map(([key, value]) => {
    const style = { ...(value as CSSProperties) }
    delete style.background
    delete style.backgroundColor
    return [key, style]
  }),
) as typeof oneLight

function JsonCodeBlock({ data }: { data: unknown }) {
  const json = JSON.stringify(data, null, 2)
  return (
    <div className="knowledge-raw">
      <SyntaxHighlighter
        language="json"
        style={jsonCodeStyle}
        PreTag="pre"
        wrapLongLines
        customStyle={{
          margin: 0,
          padding: 0,
          background: 'transparent',
          fontSize: '12px',
          lineHeight: 1.65,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
        codeTagProps={{
          style: {
            fontFamily: "ui-monospace, 'Cascadia Code', Consolas, monospace",
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          },
        }}
      >
        {json}
      </SyntaxHighlighter>
    </div>
  )
}

type PillProps = { label: string; variant: 'all' | 'area' | 'device' | 'switch' | 'rel' | 'prop' }

function SchemaPill({ label, variant }: PillProps) {
  return <span className={`neo-pill neo-pill--${variant}`}>{label}</span>
}

function relationPillClass(relation: string): string {
  if (relation === 'LOCATED_IN') return 'knowledge-table__rel-pill knowledge-table__rel-pill--located'
  if (relation === 'CONNECTED_TO') return 'knowledge-table__rel-pill knowledge-table__rel-pill--connected'
  return 'knowledge-table__rel-pill'
}

function TableNodeCell({ node }: { node?: TopologyNode }) {
  if (!node) {
    return <span className="knowledge-table__node-missing">—</span>
  }
  return (
    <div className="knowledge-table__node-cell">
      <SchemaPill label={node.type} variant={pillVariant(node.type)} />
      <span className="knowledge-table__node-name">{node.label}</span>
    </div>
  )
}

type WorkspaceProps = {
  data: TopologyResponse
  dataSource: DataSource
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
  selectedId: string | null
  onSelectNode: (id: string) => void
  drawerOpen: boolean
  onCloseDrawer: () => void
  onRunQuery?: () => void
  queryRunning?: boolean
  queryElapsed?: number
  queryMs?: number | null
}

function Neo4jWorkspace({
  data,
  dataSource,
  viewMode,
  onViewModeChange,
  selectedId,
  onSelectNode,
  drawerOpen,
  onCloseDrawer,
  onRunQuery,
  queryRunning,
  queryElapsed = 0,
  queryMs,
}: WorkspaceProps) {
  const graphChartRef = useRef<KnowledgeGraphChartHandle>(null)
  const [draftQuery, setDraftQuery] = useState('')
  const [activeQuery, setActiveQuery] = useState(DISPLAY_CYPHER)
  const [activeFrameOpen, setActiveFrameOpen] = useState(true)

  const runFromDraft = () => {
    const trimmed = draftQuery.trim()
    if (trimmed) {
      setActiveQuery(trimmed)
      setDraftQuery('')
      setActiveFrameOpen(true)
    }
    onRunQuery?.()
  }

  const handleQueryKeyDown = (e: React.KeyboardEvent, run: () => void) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      run()
    }
  }

  const nodeById = useMemo(() => {
    const map = new Map<string, TopologyNode>()
    data.nodes.forEach((n) => map.set(n.id, n))
    return map
  }, [data.nodes])
  const selectedNode = selectedId ? nodeById.get(selectedId) : undefined
  const propertyKeys = useMemo(() => collectPropertyKeys(data.nodes), [data.nodes])
  const totalNodes = data.meta?.total_nodes ?? data.nodes.length
  const totalEdges = data.meta?.total_edges ?? data.edges.length

  const detailRows = useMemo(() => {
    if (!selectedNode) return []
    const rows: { key: string; value: string }[] = []
    const internalId = selectedNode.properties._neo4j_id
    if (internalId !== undefined) {
      rows.push({ key: '<id>', value: String(internalId) })
    }
    for (const [key, value] of Object.entries(selectedNode.properties)) {
      if (key.startsWith('_')) continue
      rows.push({ key, value: JSON.stringify(value) })
    }
    return rows
  }, [selectedNode])

  const viewTabs: { key: ViewMode; label: string }[] = [
    { key: 'graph', label: '图可视化' },
    { key: 'table', label: '表格' },
    { key: 'raw', label: '原始数据' },
  ]

  const statusText =
    dataSource === 'mock'
      ? `已开始流式传输 ${totalNodes} 条记录，用时 5 ms，完成耗时 18 ms。`
      : queryMs != null
        ? `已开始流式传输 ${totalNodes} 条记录，用时 ${Math.max(1, Math.round(queryMs * 0.3))} ms，完成耗时 ${queryMs} ms。`
        : `已完成：返回 ${totalNodes} 个节点、${totalEdges} 条关系`

  return (
    <div className="knowledge-neo4j">
      <aside className="knowledge-db-panel">
        <h2 className="knowledge-db-panel__title">数据库信息</h2>

        <section className="knowledge-db-section">
          <h3>节点 ({totalNodes})</h3>
          <div className="knowledge-db-pills">
            <SchemaPill label="*" variant="all" />
            {data.meta?.node_labels.map((label) => (
              <SchemaPill key={label} label={label} variant={pillVariant(label)} />
            ))}
          </div>
        </section>

        <section className="knowledge-db-section">
          <h3>关系 ({totalEdges})</h3>
          <div className="knowledge-db-pills">
            <SchemaPill label="*" variant="rel" />
            {data.meta?.relationship_types.map((rel) => (
              <SchemaPill key={rel} label={rel} variant="rel" />
            ))}
          </div>
        </section>

        <section className="knowledge-db-section">
          <h3>属性键</h3>
          <div className="knowledge-db-pills">
            {propertyKeys.length > 0 ? (
              propertyKeys.map((key) => <SchemaPill key={key} label={key} variant="prop" />)
            ) : (
              <span className="knowledge-db-empty">—</span>
            )}
          </div>
        </section>
      </aside>

      <div className="knowledge-workspace">
        <div className="knowledge-console">
          <div className="knowledge-console__row knowledge-console__row--draft">
            <span className="knowledge-console__prompt">neo4j$</span>
            <div className="knowledge-console__field">
              <input
                type="text"
                className="knowledge-console__input"
                value={draftQuery}
                onChange={(e) => setDraftQuery(e.target.value)}
                onKeyDown={(e) => handleQueryKeyDown(e, runFromDraft)}
                placeholder="输入 Cypher 查询…"
                spellCheck={false}
                aria-label="新查询"
              />
            </div>
            <div className="knowledge-console__actions">
              <button type="button" className="knowledge-console__icon-btn" title="更多" aria-label="更多">
                <MoreHorizontal size={16} />
              </button>
              <button
                type="button"
                className="knowledge-console__icon-btn knowledge-console__icon-btn--run"
                title="运行"
                aria-label="运行查询"
                onClick={runFromDraft}
                disabled={queryRunning}
              >
                <Play size={16} fill="currentColor" />
              </button>
            </div>
          </div>

          {activeFrameOpen && (
            <div className="knowledge-console__row knowledge-console__row--active">
              <span className="knowledge-console__prompt">neo4j$</span>
              <div className="knowledge-console__field knowledge-console__field--active">
                <input
                  type="text"
                  className="knowledge-console__input"
                  value={activeQuery}
                  onChange={(e) => setActiveQuery(e.target.value)}
                  onKeyDown={(e) => handleQueryKeyDown(e, () => onRunQuery?.())}
                  spellCheck={false}
                  aria-label="Cypher 查询"
                />
              </div>
              <div className="knowledge-console__actions">
                <button type="button" className="knowledge-console__icon-btn" title="收藏" aria-label="收藏">
                  <Bookmark size={16} />
                </button>
                <button
                  type="button"
                  className="knowledge-console__icon-btn knowledge-console__icon-btn--run"
                  title="运行"
                  aria-label="运行查询"
                  onClick={onRunQuery}
                  disabled={queryRunning}
                >
                  <Play size={16} fill="currentColor" />
                </button>
                <span className="knowledge-console__timer">{formatElapsed(queryElapsed)}</span>
                <button
                  type="button"
                  className="knowledge-console__icon-btn"
                  title="关闭"
                  aria-label="关闭"
                  onClick={() => setActiveFrameOpen(false)}
                >
                  <X size={16} />
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="knowledge-results">
          <div className="knowledge-results-main">
            <div className="knowledge-result-header">
              <div className="knowledge-result-tabs" role="tablist">
                {viewTabs.map(({ key, label }) => (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={viewMode === key}
                    className={
                      viewMode === key
                        ? 'knowledge-result-tab knowledge-result-tab--active'
                        : 'knowledge-result-tab'
                    }
                    onClick={() => onViewModeChange(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {viewMode === 'graph' && (
                <div className="knowledge-result-tools">
                  <button type="button" className="knowledge-result-tools__btn" title="搜索" aria-label="搜索">
                    <Search size={16} />
                  </button>
                  <button type="button" className="knowledge-result-tools__btn" title="下载" aria-label="下载">
                    <Download size={16} />
                  </button>
                  <button type="button" className="knowledge-result-tools__btn" title="布局" aria-label="布局">
                    <Network size={16} />
                  </button>
                </div>
              )}
            </div>

            <div className="knowledge-result-body">
              {viewMode === 'graph' && (
                <div className="knowledge-graph-stage">
                  <KnowledgeGraphChart
                    ref={graphChartRef}
                    nodes={data.nodes}
                    edges={data.edges}
                    selectedId={selectedId}
                    onSelectNode={onSelectNode}
                  />
                  <div className="knowledge-graph-toolbar">
                    <button type="button" className="knowledge-graph-toolbar__btn knowledge-graph-toolbar__btn--active" title="选择">
                      <MousePointer2 size={16} />
                    </button>
                    <button
                      type="button"
                      className="knowledge-graph-toolbar__btn"
                      title="适应画布"
                      onClick={() => graphChartRef.current?.resetView()}
                    >
                      <Maximize2 size={16} />
                    </button>
                    <button
                      type="button"
                      className="knowledge-graph-toolbar__btn"
                      title="重新布局"
                      onClick={() => graphChartRef.current?.relayout()}
                    >
                      <Network size={16} />
                    </button>
                  </div>
                </div>
              )}

              {viewMode === 'table' && (
                <div className="knowledge-table-panel">
                  <div className="knowledge-table-panel__meta">
                    <span>共 {data.edges.length} 条关系</span>
                  </div>
                  <div className="knowledge-table-wrap">
                    <table className="knowledge-table">
                      <thead>
                        <tr>
                          <th>源节点</th>
                          <th className="knowledge-table__th--center">关系</th>
                          <th>目标节点</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.edges.length === 0 ? (
                          <tr>
                            <td colSpan={3} className="knowledge-table__empty">
                              暂无关系数据
                            </td>
                          </tr>
                        ) : (
                          data.edges.map((edge) => (
                            <tr key={edge.id} className="knowledge-table__row">
                              <td>
                                <TableNodeCell node={nodeById.get(edge.source)} />
                              </td>
                              <td className="knowledge-table__rel">
                                <span className={relationPillClass(edge.relation)}>{edge.relation}</span>
                              </td>
                              <td>
                                <TableNodeCell node={nodeById.get(edge.target)} />
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {viewMode === 'raw' && <JsonCodeBlock data={data} />}
            </div>
          </div>

          <aside
            className={`knowledge-node-drawer${drawerOpen ? ' knowledge-node-drawer--open' : ''}`}
            aria-hidden={!drawerOpen}
          >
            <header className="knowledge-node-drawer__header">
              <h3>节点详情</h3>
              <div className="knowledge-node-drawer__actions">
                {selectedNode && (
                  <button
                    type="button"
                    className="knowledge-node-drawer__icon-btn"
                    aria-label="复制节点信息"
                    onClick={() => copyText(JSON.stringify(selectedNode.properties, null, 2))}
                  >
                    <Copy size={16} />
                  </button>
                )}
                <button
                  type="button"
                  className="knowledge-node-drawer__icon-btn"
                  aria-label="关闭节点详情"
                  onClick={onCloseDrawer}
                >
                  <X size={18} />
                </button>
              </div>
            </header>

            {selectedNode ? (
              <div className="knowledge-node-drawer__body">
                <div className="knowledge-node-drawer__label">
                  <SchemaPill label={selectedNode.type} variant={pillVariant(selectedNode.type)} />
                </div>
                <table className="knowledge-node-props">
                  <thead>
                    <tr>
                      <th>键</th>
                      <th>值</th>
                      <th aria-hidden="true" />
                    </tr>
                  </thead>
                  <tbody>
                    {detailRows.map(({ key, value }) => (
                      <tr key={key}>
                        <td className="knowledge-node-props__key">{key}</td>
                        <td className="knowledge-node-props__value">{value}</td>
                        <td className="knowledge-node-props__copy">
                          <button
                            type="button"
                            className="knowledge-node-props__copy-btn"
                            onClick={() => copyText(value)}
                            aria-label={`复制 ${key}`}
                          >
                            <Copy size={16} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </aside>
        </div>

        <footer className="knowledge-status-bar">
          <span className="knowledge-status-bar__logo" aria-hidden="true">
            ⬡
          </span>
          <span className="knowledge-status-bar__text">{statusText}</span>
          <CheckCircle2 size={16} className="knowledge-status-bar__check" aria-hidden="true" />
        </footer>
      </div>
    </div>
  )
}

function KnowledgePanel() {
  const [viewMode, setViewMode] = useState<ViewMode>('graph')
  const [dataSource, setDataSource] = useState<DataSource>('mock')
  const [liveData, setLiveData] = useState<TopologyResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [queryElapsed, setQueryElapsed] = useState(0)
  const [queryMs, setQueryMs] = useState<number | null>(18)
  const timerRef = useRef<number | null>(null)
  const startRef = useRef<number>(0)

  const displayData = dataSource === 'mock' ? MOCK_TOPOLOGY : liveData

  const stopTimer = useCallback(() => {
    if (timerRef.current != null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const startTimer = useCallback(() => {
    stopTimer()
    startRef.current = Date.now()
    setQueryElapsed(0)
    timerRef.current = window.setInterval(() => {
      setQueryElapsed(Math.floor((Date.now() - startRef.current) / 1000))
    }, 1000)
  }, [stopTimer])

  useEffect(() => () => stopTimer(), [stopTimer])

  const loadTopology = useCallback(async () => {
    setDataSource('live')
    setLoading(true)
    setError(null)
    startTimer()
    const base = import.meta.env.VITE_API_BASE_URL ?? ''
    const token = localStorage.getItem('access_token')
    const headers: HeadersInit = { Accept: 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`

    try {
      const res = await fetch(`${base}/api/knowledge/topology`, { headers })
      const body = (await res.json().catch(() => ({}))) as TopologyResponse & { detail?: string }
      if (!res.ok) {
        const msg = typeof body.detail === 'string' ? body.detail : `请求失败 (${res.status})`
        throw new Error(msg)
      }
      if (!body.nodes?.length) {
        throw new Error('Neo4j 中暂无拓扑数据，请先导入图谱')
      }
      setLiveData(body)
      setSelectedId(null)
      setDrawerOpen(false)
      setQueryMs(Date.now() - startRef.current)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载知识库失败')
      setLiveData(null)
      setQueryMs(null)
    } finally {
      stopTimer()
      setLoading(false)
    }
  }, [startTimer, stopTimer])

  const enterMockMode = useCallback(() => {
    setDataSource('mock')
    setError(null)
    setSelectedId(null)
    setDrawerOpen(false)
    setQueryMs(18)
    setQueryElapsed(0)
  }, [])

  const handleSelectNode = useCallback((id: string) => {
    setSelectedId(id)
    setDrawerOpen(true)
  }, [])

  const handleCloseDrawer = useCallback(() => {
    setDrawerOpen(false)
    setSelectedId(null)
  }, [])

  const runQuery = useCallback(() => {
    if (dataSource === 'live') {
      void loadTopology()
    } else {
      startTimer()
      window.setTimeout(() => {
        stopTimer()
        setQueryMs(18)
      }, 400)
    }
  }, [dataSource, loadTopology, startTimer, stopTimer])

  const showError = dataSource === 'live' && !loading && error
  const showContent = dataSource === 'mock' || (Boolean(liveData) && !loading && !error)

  const toolbar = (
    <div className="knowledge-page__toolbar">
      <div className="knowledge-page__toolbar-info">
        {dataSource === 'mock' && <span className="knowledge-page__badge">演示数据</span>}
        {loading && <span className="knowledge-page__badge knowledge-page__badge--loading">连接 Neo4j…</span>}
      </div>
      <div className="knowledge-page__toolbar-actions">
        <button
          type="button"
          className={
            dataSource === 'mock'
              ? 'knowledge-page__btn knowledge-page__btn--active'
              : 'knowledge-page__btn'
          }
          onClick={enterMockMode}
        >
          模拟
        </button>
        <button
          type="button"
          className="knowledge-page__btn"
          onClick={() => void loadTopology()}
          disabled={loading}
        >
          <RefreshCw size={14} className={loading ? 'knowledge-spin' : undefined} />
          刷新
        </button>
      </div>
    </div>
  )

  return (
    <div className="knowledge-page">
      {showError && (
        <>
          {toolbar}
          <div className="knowledge-page__error">
            <p>{error}</p>
            <p>请启动 Neo4j（bolt://localhost:7687）或点击「模拟」查看演示。</p>
            <div className="knowledge-page__error-actions">
              <button type="button" className="knowledge-page__btn knowledge-page__btn--active" onClick={enterMockMode}>
                模拟
              </button>
              <button type="button" className="knowledge-page__btn" onClick={() => void loadTopology()}>
                重试
              </button>
            </div>
          </div>
        </>
      )}

      {showContent && displayData && (
        <div className="knowledge-page__body">
          <div className="knowledge-shell">
            {toolbar}
            {loading && dataSource === 'live' && (
              <div className="knowledge-page__overlay">正在连接 Neo4j…</div>
            )}
            <Neo4jWorkspace
              data={displayData}
              dataSource={dataSource}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              selectedId={selectedId}
              onSelectNode={handleSelectNode}
              drawerOpen={drawerOpen}
              onCloseDrawer={handleCloseDrawer}
              onRunQuery={runQuery}
              queryRunning={loading}
              queryElapsed={queryElapsed}
              queryMs={queryMs}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default KnowledgePanel
