import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { PREDICTION_STATIC, type HorizonKey } from './predictionStaticData'

const { allSeries, kpi, rolePie, hourlyBar, capacity } = PREDICTION_STATIC

const labels = allSeries.map((p) => p.label)
const q10 = allSeries.map((p) => p.q10)
const q50 = allSeries.map((p) => p.q50)
const q90 = allSeries.map((p) => p.q90)
const bandWidth = q10.map((v, i) => Number((q90[i] - v).toFixed(4)))

type HorizonPoint = {
  hour: number
  label: string
  q10: number
  q50: number
  q90: number
}

function hasSignal(p: HorizonPoint) {
  return p.q10 > 0 || p.q50 > 0 || p.q90 > 0
}

function trimHorizonPoints(raw: readonly HorizonPoint[], key: HorizonKey) {
  let pts = raw
  if (key === 'front') pts = raw.filter((p) => p.hour <= 12)
  if (key === 'back') pts = raw.filter((p) => p.hour > 12)
  const first = pts.findIndex(hasSignal)
  if (first < 0) return pts
  let last = pts.length - 1
  while (last > first && !hasSignal(pts[last])) last -= 1
  return pts.slice(first, last + 1)
}

function seriesFromHorizon(key: HorizonKey) {
  const pts = trimHorizonPoints(PREDICTION_STATIC.horizonSeries[key], key)
  return {
    labels: pts.map((p) => p.label),
    q10: pts.map((p) => p.q10),
    q50: pts.map((p) => p.q50),
    q90: pts.map((p) => p.q90),
  }
}

/** 24h 全网负载预测：Q50 + Q10~Q90 置信带 */
export function buildPredictionForecastOption(): EChartsOption {
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const list = params as { dataIndex: number }[]
        const idx = list[0]?.dataIndex ?? -1
        if (idx < 0) return ''
        return [
          `<strong>${labels[idx]}</strong>`,
          `Q10：${q10[idx]}%`,
          `Q50：${q50[idx]}%`,
          `Q90：${q90[idx]}%`,
        ].join('<br/>')
      },
    },
    legend: {
      data: ['预测中位数 Q50', 'Q10~Q90 置信带'],
      textStyle: { color: '#2b6ec8', fontSize: 10 },
      top: 0,
      right: 0,
    },
    grid: { left: '2%', right: '3%', top: '18%', bottom: '6%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: labels,
      axisLabel: { color: '#2b6ec8', fontSize: 9, interval: 2 },
      axisLine: { lineStyle: { color: 'rgba(43,110,200,0.35)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '负载 %',
      nameTextStyle: { color: '#2b6ec8', fontSize: 10 },
      axisLabel: { color: '#2b6ec8', formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(43,110,200,0.12)' } },
      max: Math.ceil(Math.max(...q90, kpi.peakQ90Pct) * 1.25),
    },
    series: [
      {
        name: 'Q10基线',
        type: 'line',
        stack: 'ci',
        data: q10,
        lineStyle: { opacity: 0 },
        symbol: 'none',
        silent: true,
      },
      {
        name: 'Q10~Q90 置信带',
        type: 'line',
        stack: 'ci',
        data: bandWidth,
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(24,144,255,0.22)' },
        symbol: 'none',
        silent: true,
      },
      {
        name: '预测中位数 Q50',
        type: 'line',
        smooth: true,
        data: q50,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: '#1890ff', width: 2 },
        itemStyle: { color: '#1890ff' },
      },
    ],
  }
}

export type LiveForecastSeries = {
  labels: string[]
  q10: number[]
  q50: number[]
  q90: number[]
}

function toPctValues(values: number[]): number[] {
  return values.map((v) => Number((v <= 1 ? v * 100 : v).toFixed(3)))
}

/** 与静态主图相同样式，数据来自 TimesFM MCP */
export function buildPredictionForecastOptionFromLive(series: LiveForecastSeries): EChartsOption {
  const { labels: ls, q10: rawQ10, q50: rawQ50, q90: rawQ90 } = series
  const q10p = toPctValues(rawQ10)
  const q50p = toPctValues(rawQ50)
  const q90p = toPctValues(rawQ90)
  const band = q10p.map((v, i) => Number((q90p[i] - v).toFixed(4)))
  const yMax = Math.ceil(Math.max(...q90p, ...q50p, 1) * 1.25)
  const xInterval = ls.length > 12 ? Math.max(1, Math.floor(ls.length / 6)) : ls.length > 6 ? 1 : 0

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const list = params as { dataIndex: number }[]
        const idx = list[0]?.dataIndex ?? -1
        if (idx < 0) return ''
        return [
          `<strong>${ls[idx]}</strong>`,
          `Q10：${q10p[idx]}%`,
          `Q50：${q50p[idx]}%`,
          `Q90：${q90p[idx]}%`,
        ].join('<br/>')
      },
    },
    legend: {
      data: ['预测中位数 Q50', 'Q10~Q90 置信带'],
      textStyle: { color: '#2b6ec8', fontSize: 10 },
      top: 0,
      right: 0,
    },
    grid: { left: '2%', right: '3%', top: '18%', bottom: '6%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: ls,
      axisLabel: { color: '#2b6ec8', fontSize: 9, interval: xInterval },
      axisLine: { lineStyle: { color: 'rgba(43,110,200,0.35)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '负载 %',
      nameTextStyle: { color: '#2b6ec8', fontSize: 10 },
      axisLabel: { color: '#2b6ec8', formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(43,110,200,0.12)' } },
      max: yMax,
    },
    series: [
      {
        name: 'Q10基线',
        type: 'line',
        stack: 'ci',
        data: q10p,
        lineStyle: { opacity: 0 },
        symbol: 'none',
        silent: true,
      },
      {
        name: 'Q10~Q90 置信带',
        type: 'line',
        stack: 'ci',
        data: band,
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(24,144,255,0.22)' },
        symbol: 'none',
        silent: true,
      },
      {
        name: '预测中位数 Q50',
        type: 'line',
        smooth: true,
        data: q50p,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: '#1890ff', width: 2 },
        itemStyle: { color: '#1890ff' },
      },
    ],
  }
}

export type LiveRoleSeries = {
  name: string
  color: string
  q50: number[]
}

/** 分区预测对比 — 数据来自 TimesFM MCP（多设备并行预测） */
export function buildRoleForecastOptionFromLive(
  labels: string[],
  roles: LiveRoleSeries[],
): EChartsOption {
  const xInterval = labels.length > 14 ? 2 : labels.length > 8 ? 1 : 0
  const allVals = roles.flatMap((r) => toPctValues(r.q50))
  const yMax = Math.ceil(Math.max(...allVals, 1) * 1.25)

  return {
    tooltip: { trigger: 'axis' },
    legend: {
      data: roles.map((r) => r.name),
      textStyle: { color: '#2b6ec8', fontSize: 10 },
      top: 0,
    },
    grid: { left: '2%', right: '3%', top: '22%', bottom: '6%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: labels,
      axisLabel: { color: '#2b6ec8', fontSize: 9, interval: xInterval },
      axisLine: { lineStyle: { color: 'rgba(43,110,200,0.35)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: 'Q50 负载 %',
      nameTextStyle: { color: '#2b6ec8', fontSize: 10 },
      axisLabel: { color: '#2b6ec8', formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(43,110,200,0.12)' } },
      max: yMax,
    },
    series: roles.map((r) => ({
      name: r.name,
      type: 'line' as const,
      smooth: true,
      data: toPctValues(r.q50),
      symbol: 'none',
      lineStyle: { width: 2, color: r.color },
      itemStyle: { color: r.color },
    })),
  }
}

/** 角色平均负载占比（玫瑰图） */
export function buildRolePieOption(): EChartsOption {
  return {
    tooltip: { trigger: 'item', formatter: '{b}<br/>平均 Q50：{c}%' },
    series: [
      {
        name: '角色负载',
        type: 'pie',
        radius: ['10%', '70%'],
        center: ['50%', '50%'],
        roseType: 'radius',
        data: rolePie.map((p) => ({ name: p.name, value: p.value })),
        label: { fontSize: 10, color: '#2b6ec8' },
        labelLine: { length: 8, length2: 10 },
      },
    ],
    color: ['#1890ff', '#52c41a', '#faad14'],
  }
}

/** 分时段 Q50 柱状图 */
export function buildHourlyBarOption(): EChartsOption {
  return {
    tooltip: { trigger: 'axis' },
    grid: {
      left: '0',
      right: '3%',
      bottom: '3%',
      top: '8%',
      containLabel: true,
      show: true,
      borderColor: 'rgba(43, 110, 200, 0.25)',
    },
    xAxis: {
      type: 'category',
      data: hourlyBar.map((p) => p.label),
      axisTick: { show: false },
      axisLabel: { color: '#2b6ec8', fontSize: 9 },
    },
    yAxis: {
      type: 'value',
      axisTick: { show: false },
      axisLabel: { color: '#2b6ec8', formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(43, 110, 200, 0.15)' } },
    },
    series: [
      {
        name: 'Q50 预测负载',
        type: 'bar',
        barWidth: '55%',
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#5eb3ff' },
            { offset: 1, color: '#2b6ec8' },
          ]),
        },
        data: hourlyBar.map((p) => p.q50),
      },
    ],
  }
}

/** 分位曲线（按预测窗口切换 Q10/Q50/Q90） */
export function buildHorizonQuantileOption(key: HorizonKey): EChartsOption {
  const { labels: ls, q10: q10h, q50: q50h, q90: q90h } = seriesFromHorizon(key)
  const allVals = [...q10h, ...q50h, ...q90h]
  const dataMin = Math.min(...allVals)
  const dataMax = Math.max(...allVals)
  const span = Math.max(dataMax - dataMin, 0.25)
  const yMin = Math.max(0, Number((dataMin - span * 0.06).toFixed(2)))
  const yMax = Number((dataMax + span * 0.06).toFixed(2))
  const xInterval = ls.length > 14 ? 2 : ls.length > 8 ? 1 : 0

  return {
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['Q10', 'Q50', 'Q90'],
      top: 2,
      right: 0,
      itemWidth: 10,
      itemHeight: 6,
      itemGap: 5,
      textStyle: { color: '#2b6ec8', fontSize: 8 },
    },
    grid: {
      show: true,
      top: 28,
      left: 30,
      right: 6,
      bottom: 6,
      borderColor: 'rgba(43, 110, 200, 0.25)',
      containLabel: false,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: ls,
      axisLabel: {
        color: '#2b6ec8',
        fontSize: 11,
        interval: xInterval,
        margin: 4,
        hideOverlap: true,
      },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    yAxis: {
      type: 'value',
      min: yMin,
      max: yMax,
      name: '负载%',
      nameTextStyle: { color: '#2b6ec8', fontSize: 11, padding: [0, 0, 0, 0] },
      nameGap: 2,
      nameLocation: 'end',
      axisLabel: {
        color: '#2b6ec8',
        fontSize: 11,
        formatter: '{value}',
        margin: 2,
        width: 30,
        align: 'right',
      },
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: 'rgba(43,110,200,0.12)' } },
      splitNumber: 3,
    },
    series: [
      { name: 'Q10', type: 'line', smooth: true, data: q10h, symbol: 'none', lineStyle: { color: '#91d5ff', width: 1.5 } },
      { name: 'Q50', type: 'line', smooth: true, data: q50h, symbol: 'none', lineStyle: { color: '#1890ff', width: 2 } },
      { name: 'Q90', type: 'line', smooth: true, data: q90h, symbol: 'none', lineStyle: { color: '#0050b3', width: 1.5 } },
    ],
  }
}

/** 峰值容量占用率仪表盘 */
export function buildCapacityGaugeOption(): EChartsOption {
  const util = capacity.utilizationPct
  return {
    series: [
      {
        type: 'pie',
        radius: ['110%', '130%'],
        center: ['50%', '92%'],
        label: { show: false },
        startAngle: 180,
        data: [
          {
            value: util,
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: util > 70 ? '#ed3f35' : '#5eb3ff' },
                { offset: 1, color: util > 70 ? '#c62828' : '#2b6ec8' },
              ]),
            },
          },
          { value: 100 - util, itemStyle: { color: '#c5dff5' } },
          { value: 100, itemStyle: { color: 'transparent' } },
        ],
      },
    ],
  }
}
