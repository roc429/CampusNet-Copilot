import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Maximize2,
  Minimize2,
  Network,
  RotateCcw,
  Search,
  Shield,
  Smartphone,
  Target,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { fetchRagTest, type RagTestResponse, type RagTopologyEdge } from '../api/agentApi'
import KnowledgeGraphChart, {
  type GraphEdge,
  type GraphNode,
  type KnowledgeGraphChartHandle,
} from './KnowledgeGraphChart'
import './RagSearchPanel.css'

type Props = {
  defaultDeviceId?: string
  defaultQuery?: string
}

const RELATION_LEGEND = [
  { key: 'AFFECTS', label: 'AFFECTS', color: '#b794f6' },
  { key: 'LOCATED_IN', label: 'LOCATED_IN', color: '#4fd1c5' },
  { key: 'CONNECTED_TO', label: 'CONNECTED_TO', color: '#60a5fa' },
] as const

const NODE_LEGEND = [
  { type: 'Device', label: '设备 (AP)', color: '#b794f6' },
  { type: 'Switch', label: '交换机 (SW)', color: '#60a5fa' },
  { type: 'Area', label: '区域 (AREA)', color: '#4fd1c5' },
] as const

function inferNodeType(id: string): string {
  if (id.startsWith('AREA-')) return 'Area'
  if (id.startsWith('SW-') || id.startsWith('CORE-')) return 'Switch'
  if (id.startsWith('AP-')) return 'Device'
  return 'Node'
}

function topologyChainToGraph(chain: RagTopologyEdge[]): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodeMap = new Map<string, GraphNode>()
  const edges: GraphEdge[] = []

  chain.forEach((item, index) => {
    for (const id of [item.source, item.target]) {
      if (!nodeMap.has(id)) {
        nodeMap.set(id, { id, label: id, type: inferNodeType(id) })
      }
    }
    edges.push({
      id: `rag-edge-${index}`,
      source: item.source,
      target: item.target,
      relation: item.relation,
    })
  })

  return { nodes: [...nodeMap.values()], edges }
}

export default function RagSearchPanel({
  defaultDeviceId = 'AP-EXAM-302',
  defaultQuery = '302考场考试系统卡顿',
}: Props) {
  const chartRef = useRef<KnowledgeGraphChartHandle>(null)
  const graphShellRef = useRef<HTMLDivElement>(null)

  const [deviceId, setDeviceId] = useState(defaultDeviceId)
  const [query, setQuery] = useState(defaultQuery)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<RagTestResponse | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)

  useEffect(() => {
    const onFsChange = () => setFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onFsChange)
    return () => document.removeEventListener('fullscreenchange', onFsChange)
  }, [])

  const graphData = useMemo(() => {
    if (!result?.topology_chain?.length) return null
    return topologyChainToGraph(result.topology_chain)
  }, [result])

  const activeRelations = useMemo(() => {
    if (!result?.topology_chain?.length) return RELATION_LEGEND
    const keys = new Set(result.topology_chain.map((e) => e.relation))
    return RELATION_LEGEND.filter((r) => keys.has(r.key))
  }, [result])

  const activeNodeTypes = useMemo(() => {
    if (!graphData?.nodes.length) return NODE_LEGEND
    const types = new Set(graphData.nodes.map((n) => n.type))
    return NODE_LEGEND.filter((n) => types.has(n.type))
  }, [graphData])

  async function handleSearch() {
    const q = query.trim()
    const d = deviceId.trim()
    if (!q || !d) return

    setLoading(true)
    setError(null)
    setSelectedNodeId(d)
    try {
      const data = await fetchRagTest(d, q)
      setResult(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : '检索失败')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  async function toggleFullscreen() {
    const el = graphShellRef.current
    if (!el) return
    if (!document.fullscreenElement) {
      await el.requestFullscreen().catch(() => undefined)
      setFullscreen(true)
    } else {
      await document.exitFullscreen().catch(() => undefined)
      setFullscreen(false)
    }
  }

  return (
    <section className="rag-search">
      <div className="rag-search__toolbar">
        <label className="rag-search__input-wrap">
          <span className="rag-search__input-label">设备 ID</span>
          <div className="rag-search__input-box">
            <Smartphone size={16} className="rag-search__input-icon" aria-hidden="true" />
            <input
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              placeholder="AP-EXAM-302"
            />
          </div>
        </label>
        <label className="rag-search__input-wrap rag-search__input-wrap--grow">
          <span className="rag-search__input-label">查询</span>
          <div className="rag-search__input-box">
            <Search size={16} className="rag-search__input-icon" aria-hidden="true" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="输入检索问题"
              onKeyDown={(e) => e.key === 'Enter' && void handleSearch()}
            />
          </div>
        </label>
        <button
          type="button"
          className="rag-search__submit"
          disabled={loading}
          onClick={() => void handleSearch()}
        >
          <Search size={16} aria-hidden="true" />
          {loading ? '检索中…' : '检索'}
        </button>
      </div>

      {result?.source ? (
        <div className="rag-search__source">
          数据源：<span className="rag-search__source-tag">{result.source}</span>
        </div>
      ) : null}

      {error ? <div className="rag-search__error">{error}</div> : null}

      {result ? (
        <div className="rag-search__body">
          {result.evidence_snapshot ? (
            <article className="rag-search__snapshot">
              <header className="rag-search__section-head">
                <Shield size={18} aria-hidden="true" />
                <h4>证据快照</h4>
              </header>
              <p>{result.evidence_snapshot}</p>
            </article>
          ) : null}

          <div className="rag-search__split">
            <aside className="rag-search__hits-panel">
              <header className="rag-search__section-head">
                <Target size={18} aria-hidden="true" />
                <h4>语义命中</h4>
              </header>
              {result.semantic_hits && result.semantic_hits.length > 0 ? (
                <div className="rag-search__hits-list">
                  {result.semantic_hits.map((hit, i) => (
                    <article key={i} className="rag-search__hit-card">
                      <span className="rag-search__hit-index">#{i + 1}</span>
                      <p>{hit}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="rag-search__empty-hint">暂无语义命中</p>
              )}
            </aside>

            <div
              className={`rag-search__graph-panel${fullscreen ? ' rag-search__graph-panel--fullscreen' : ''}`}
              ref={graphShellRef}
            >
              <header className="rag-search__graph-head">
                <div className="rag-search__section-head">
                  <Network size={18} aria-hidden="true" />
                  <h4>拓扑链 · 力导向图</h4>
                </div>
                <div className="rag-search__graph-tools">
                  <button type="button" title="放大" onClick={() => chartRef.current?.zoomIn()}>
                    <ZoomIn size={15} aria-hidden="true" />
                    放大
                  </button>
                  <button type="button" title="缩小" onClick={() => chartRef.current?.zoomOut()}>
                    <ZoomOut size={15} aria-hidden="true" />
                    缩小
                  </button>
                  <button type="button" title="重置" onClick={() => chartRef.current?.resetView()}>
                    <RotateCcw size={15} aria-hidden="true" />
                    重置
                  </button>
                  <button type="button" title="全屏" onClick={() => void toggleFullscreen()}>
                    {fullscreen ? (
                      <Minimize2 size={15} aria-hidden="true" />
                    ) : (
                      <Maximize2 size={15} aria-hidden="true" />
                    )}
                    {fullscreen ? '退出' : '全屏'}
                  </button>
                </div>
              </header>

              {graphData && graphData.nodes.length > 0 ? (
                <>
                  <div className="rag-search__graph">
                    <KnowledgeGraphChart
                      ref={chartRef}
                      nodes={graphData.nodes}
                      edges={graphData.edges}
                      selectedId={selectedNodeId}
                      onSelectNode={setSelectedNodeId}
                      showLegend={false}
                    />
                  </div>
                  <footer className="rag-search__legend">
                    <div className="rag-search__legend-group">
                      {activeRelations.map((rel) => (
                        <span key={rel.key} className="rag-search__legend-item">
                          <i
                            className="rag-search__legend-line"
                            style={{ borderColor: rel.color }}
                            aria-hidden="true"
                          />
                          {rel.label}
                        </span>
                      ))}
                    </div>
                    <div className="rag-search__legend-group">
                      {activeNodeTypes.map((node) => (
                        <span key={node.type} className="rag-search__legend-item">
                          <i
                            className="rag-search__legend-dot"
                            style={{ background: node.color }}
                            aria-hidden="true"
                          />
                          {node.label}
                        </span>
                      ))}
                    </div>
                  </footer>
                </>
              ) : (
                <p className="rag-search__empty-hint rag-search__empty-hint--graph">暂无拓扑链数据</p>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
