import { useCallback, useEffect, useMemo, useState } from 'react'
import type { EChartsOption } from 'echarts'
import * as echarts from 'echarts'
import ItemWrap from '../ItemWrap'
import { fetchPortLoadSeries, type LoadSeriesPoint } from '../monitorScreenApi'
import { MS_THEME } from '../theme'
import { useEchart } from '../useEchart'

const VISIBLE_POINTS = 6

function loadZoomRange(length: number) {
  if (length <= VISIBLE_POINTS) {
    return { startValue: 0, endValue: Math.max(length - 1, 0) }
  }
  return { startValue: length - VISIBLE_POINTS, endValue: length - 1 }
}

export default function DeviceOverview() {
  const [series, setSeries] = useState<LoadSeriesPoint[]>([])

  const load = useCallback(async () => {
    const res = await fetchPortLoadSeries()
    if (res.success) setSeries(res.data)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const options = useMemo<EChartsOption>(() => {
    const total = series.length
    const { startValue, endValue } = loadZoomRange(total)

    return {
      animation: false,
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255,255,255,0.96)',
        borderColor: MS_THEME.primary,
        textStyle: { color: MS_THEME.text },
        valueFormatter: (v) => `${v}%`,
      },
      grid: { left: 4, right: 20, bottom: 48, top: 38, containLabel: true },
      dataZoom: [
        {
          type: 'slider',
          xAxisIndex: 0,
          startValue,
          endValue,
          filterMode: 'none',
          realtime: true,
          throttle: 0,
          showDetail: false,
          brushSelect: false,
          height: 22,
          bottom: 8,
          borderColor: MS_THEME.borderSoft,
          backgroundColor: 'rgba(24, 144, 255, 0.08)',
          fillerColor: 'rgba(255, 184, 0, 0.22)',
          handleSize: '100%',
          handleStyle: {
            color: MS_THEME.accent,
            borderColor: MS_THEME.accent,
            borderWidth: 1,
          },
          moveHandleSize: 8,
          moveHandleStyle: {
            color: MS_THEME.accent,
            borderColor: MS_THEME.accent,
            borderWidth: 1,
          },
          dataBackground: {
            lineStyle: { color: 'rgba(255, 184, 0, 0.35)', width: 1 },
            areaStyle: { color: 'rgba(255, 184, 0, 0.12)' },
          },
          selectedDataBackground: {
            lineStyle: { color: MS_THEME.accent, width: 1 },
            areaStyle: { color: 'rgba(255, 184, 0, 0.2)' },
          },
          textStyle: { color: MS_THEME.textSecondary, fontSize: 11 },
        },
        {
          type: 'inside',
          xAxisIndex: 0,
          startValue,
          endValue,
          filterMode: 'none',
          throttle: 0,
          zoomOnMouseWheel: false,
          moveOnMouseWheel: true,
          moveOnMouseMove: false,
        },
      ],
      xAxis: {
        type: 'category',
        data: series.map((p) => p.time),
        boundaryGap: false,
        axisLine: { lineStyle: { color: MS_THEME.axisLine } },
        axisLabel: {
          color: MS_THEME.textSecondary,
          fontSize: 15,
          margin: 10,
          interval: 0,
          showMaxLabel: true,
          showMinLabel: true,
          hideOverlap: false,
        },
      },
      yAxis: {
        type: 'value',
        name: '负载%',
        nameTextStyle: { color: MS_THEME.textSecondary, fontSize: 15 },
        nameGap: 10,
        splitLine: { lineStyle: { color: MS_THEME.gridLine } },
        axisLine: { lineStyle: { color: MS_THEME.axisLine } },
        axisLabel: { color: MS_THEME.textSecondary, fontSize: 15, margin: 8 },
      },
      series: [
        {
          name: '端口平均负载',
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          data: series.map((p) => p.avgLoadPct),
          lineStyle: { width: 2, color: MS_THEME.accent },
          itemStyle: { color: MS_THEME.accent },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(255, 184, 0, 0.35)' },
              { offset: 1, color: 'rgba(255, 184, 0, 0.02)' },
            ]),
          },
        },
      ],
    }
  }, [series])

  const { elRef } = useEchart(options)

  return (
    <ItemWrap title="端口负载率时序图" className="ms-port-load-panel">
      <div ref={elRef} className="ms-chart-fill ms-chart-fill--offset" />
    </ItemWrap>
  )
}
