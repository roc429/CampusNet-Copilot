import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react'
import * as echarts from 'echarts'
import type { ECharts, EChartsOption } from 'echarts'

export type GraphNode = {
  id: string
  label: string
  type: string
}

export type GraphEdge = {
  id: string
  source: string
  target: string
  relation: string
}

export type KnowledgeGraphChartHandle = {
  resetView: () => void
  relayout: () => void
  zoomIn: () => void
  zoomOut: () => void
}

type Props = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedId: string | null
  onSelectNode: (id: string) => void
  showLegend?: boolean
}

/** 与参考视频 / 左侧数据库标签配色一致 */
const CATEGORY_STYLE: Record<string, string> = {
  Area: '#4fd1c5',
  Device: '#b794f6',
  Switch: '#60a5fa',
  Node: '#94a3b8',
}

function buildCategories(nodeTypes: string[]) {
  return nodeTypes.map((name) => ({
    name,
    itemStyle: { color: CATEGORY_STYLE[name] ?? '#94a3b8' },
  }))
}

/** 超过阈值时拆成两行，避免长标签横向撑开遮挡连线 */
function formatNodeLabel(text: string, maxSingleLine = 8): string {
  const trimmed = text.trim()
  if (trimmed.length <= maxSingleLine) return trimmed
  const mid = Math.ceil(trimmed.length / 2)
  return `${trimmed.slice(0, mid)}\n${trimmed.slice(mid)}`
}

function collectAdjacentIds(selectedId: string | null, edges: GraphEdge[]): Set<string> {
  const ids = new Set<string>()
  if (!selectedId) return ids
  ids.add(selectedId)
  for (const edge of edges) {
    if (edge.source === selectedId) ids.add(edge.target)
    if (edge.target === selectedId) ids.add(edge.source)
  }
  return ids
}

function buildOption(
  nodes: GraphNode[],
  edges: GraphEdge[],
  selectedId: string | null,
  showLegend: boolean,
): EChartsOption {
  const nodeTypes = [...new Set(nodes.map((n) => n.type || 'Node'))]
  const categories = buildCategories(nodeTypes)
  const adjacentIds = collectAdjacentIds(selectedId, edges)
  const hasSelection = Boolean(selectedId)

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#e2e8f0',
      textStyle: { color: '#2d3748', fontSize: 12 },
      formatter: (params) => {
        const p = params as { dataType?: string; data?: { name?: string; value?: number } }
        const data = p.data
        if (!data) return ''
        if (p.dataType === 'edge') {
          return `<strong>${data.name ?? ''}</strong>`
        }
        const title = String((data as { rawName?: string }).rawName ?? data.name ?? '').replace(
          /\n/g,
          '',
        )
        return `<div style="font-weight:600">${title}</div>`
      },
    },
    legend: {
      show: showLegend && nodeTypes.length > 0,
      orient: 'horizontal',
      bottom: 6,
      left: 'center',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: '#718096', fontSize: 11 },
      data: nodeTypes,
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        focusNodeAdjacency: !hasSelection,
        categories,
        label: {
          show: true,
          position: 'bottom',
          distance: 12,
          color: '#4a5568',
          fontSize: 14,
          fontWeight: 400,
          lineHeight: 18,
        },
        edgeLabel: {
          show: true,
          fontSize: 11,
          fontWeight: 500,
          color: '#475569',
          formatter: (params) => {
            const name = (params.data as { name?: string })?.name
            return name ?? ''
          },
        },
        lineStyle: {
          color: '#64748b',
          width: 2.5,
          opacity: 0.92,
          curveness: 0.22,
          type: [7, 5],
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [0, 11],
        data: nodes.map((node) => {
          const isSelected = node.id === selectedId
          const isAdjacent = hasSelection && adjacentIds.has(node.id) && !isSelected
          const isDimmed = hasSelection && !adjacentIds.has(node.id)
          const color = CATEGORY_STYLE[node.type] ?? CATEGORY_STYLE.Node
          const displayName = formatNodeLabel(node.label)
          const isMultiline = displayName.includes('\n')
          return {
            id: node.id,
            name: displayName,
            rawName: node.label,
            category: node.type || 'Node',
            symbolSize: isSelected ? 52 : isAdjacent ? 46 : 42,
            itemStyle: {
              color,
              opacity: isDimmed ? 0.28 : 1,
              borderColor: '#ffffff',
              borderWidth: isSelected ? 4 : 2,
              shadowBlur: isSelected ? 22 : isAdjacent ? 10 : 6,
              shadowColor: isSelected
                ? `${color}88`
                : isAdjacent
                  ? 'rgba(99, 179, 237, 0.28)'
                  : 'rgba(45, 55, 72, 0.12)',
            },
            label: {
              fontSize: 14,
              fontWeight: isSelected || isAdjacent ? 600 : 400,
              color: isDimmed ? '#a0aec0' : isSelected ? '#2c5282' : '#4a5568',
              lineHeight: 18,
              distance: isMultiline ? 14 : 12,
              opacity: isDimmed ? 0.45 : 1,
            },
          }
        }),
        links: edges.map((edge) => {
          const isHighlight =
            hasSelection && (edge.source === selectedId || edge.target === selectedId)
          const isDimmed = hasSelection && !isHighlight
          return {
            source: edge.source,
            target: edge.target,
            name: edge.relation,
            lineStyle: {
              color: isHighlight ? '#3182ce' : '#64748b',
              width: isHighlight ? 3.5 : 2.5,
              opacity: isDimmed ? 0.16 : isHighlight ? 1 : 0.92,
            },
            label: {
              color: isHighlight ? '#2563eb' : isDimmed ? '#cbd5e0' : '#475569',
              opacity: isDimmed ? 0.4 : 1,
            },
          }
        }),
        force: {
          initLayout: 'circular',
          repulsion: 420,
          gravity: 0.04,
          edgeLength: [140, 220],
          friction: 0.55,
          layoutAnimation: true,
        },
        emphasis: {
          focus: 'adjacency',
          scale: 1.06,
          itemStyle: {
            borderColor: '#ffffff',
            borderWidth: 3,
            shadowBlur: 16,
            shadowColor: 'rgba(99, 179, 237, 0.35)',
          },
          lineStyle: { width: 3, color: '#3182ce', opacity: 1 },
          edgeLabel: { color: '#2563eb', fontWeight: 500 },
          label: { fontWeight: 600, color: '#2c5282' },
        },
        blur: {
          itemStyle: { opacity: 0.2 },
          label: { opacity: 0.35 },
          lineStyle: { opacity: 0.12 },
        },
      },
    ],
  }
}

const KnowledgeGraphChart = forwardRef<KnowledgeGraphChartHandle, Props>(function KnowledgeGraphChart(
  { nodes, edges, selectedId, onSelectNode, showLegend = true },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<ECharts | null>(null)
  const layoutSeedRef = useRef(0)

  const option = useMemo(
    () => buildOption(nodes, edges, selectedId, showLegend),
    [nodes, edges, selectedId, showLegend],
  )

  useImperativeHandle(
    ref,
    () => ({
      resetView() {
        layoutSeedRef.current += 1
        chartRef.current?.dispatchAction({ type: 'restore' })
        chartRef.current?.setOption(buildOption(nodes, edges, selectedId, showLegend), { notMerge: true })
      },
      relayout() {
        layoutSeedRef.current += 1
        chartRef.current?.setOption(buildOption(nodes, edges, selectedId, showLegend), { notMerge: true })
      },
      zoomIn() {
        const chart = chartRef.current
        if (!chart) return
        const series = (chart.getOption() as { series?: Array<{ zoom?: number }> }).series?.[0]
        const current = typeof series?.zoom === 'number' ? series.zoom : 1
        chart.setOption({ series: [{ zoom: Math.min(current * 1.25, 5) }] })
      },
      zoomOut() {
        const chart = chartRef.current
        if (!chart) return
        const series = (chart.getOption() as { series?: Array<{ zoom?: number }> }).series?.[0]
        const current = typeof series?.zoom === 'number' ? series.zoom : 1
        chart.setOption({ series: [{ zoom: Math.max(current / 1.25, 0.35) }] })
      },
    }),
    [nodes, edges, selectedId, showLegend],
  )

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = echarts.init(el, undefined, { renderer: 'canvas' })
    chartRef.current = chart

    const onClick = (params: unknown) => {
      const p = params as { dataType?: string; data?: { id?: string } }
      if (p.dataType === 'node' && p.data?.id) {
        onSelectNode(p.data.id)
      }
    }
    chart.on('click', onClick)

    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(el)

    return () => {
      ro.disconnect()
      chart.off('click', onClick)
      chart.dispose()
      chartRef.current = null
    }
  }, [onSelectNode])

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true })
  }, [option])

  return <div ref={containerRef} className="knowledge-graph-chart" role="img" aria-label="知识图谱力导向图" />
})

export default KnowledgeGraphChart
