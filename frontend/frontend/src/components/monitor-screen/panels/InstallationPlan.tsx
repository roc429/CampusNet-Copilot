import { useCallback, useEffect, useMemo, useState } from 'react'
import type { EChartsOption } from 'echarts'
import ItemWrap from '../ItemWrap'
import { fetchLossHealthSeries, type LossHealthPoint } from '../monitorScreenApi'
import { MS_THEME } from '../theme'
import { useEchart } from '../useEchart'

export default function InstallationPlan() {
  const [series, setSeries] = useState<LossHealthPoint[]>([])

  const load = useCallback(async () => {
    const res = await fetchLossHealthSeries()
    if (res.success) setSeries(res.data)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const options = useMemo<EChartsOption>(
    () => ({
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255,255,255,0.96)',
        borderColor: MS_THEME.primary,
        textStyle: { color: MS_THEME.text },
      },
      legend: {
        data: ['健康分', '丢包率'],
        textStyle: { color: MS_THEME.textSecondary, fontSize: 11 },
        top: 0,
      },
      grid: { left: '50px', right: '50px', bottom: '30px', top: '28px' },
      xAxis: {
        type: 'category',
        data: series.map((p) => p.time),
        axisLine: { lineStyle: { color: MS_THEME.axisLine } },
        axisLabel: { color: MS_THEME.textSecondary, fontSize: 10 },
      },
      yAxis: [
        {
          type: 'value',
          name: '健康分',
          min: 90,
          max: 100,
          splitLine: { lineStyle: { color: MS_THEME.gridLine } },
          axisLine: { lineStyle: { color: MS_THEME.axisLine } },
          axisLabel: { color: MS_THEME.textSecondary, fontSize: 10 },
        },
        {
          type: 'value',
          name: '丢包%',
          splitLine: { show: false },
          axisLine: { lineStyle: { color: MS_THEME.axisLine } },
          axisLabel: { color: MS_THEME.textSecondary, fontSize: 10, formatter: '{value}%' },
        },
      ],
      series: [
        {
          name: '健康分',
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          data: series.map((p) => p.healthScore),
          itemStyle: { color: MS_THEME.teal },
          lineStyle: { color: MS_THEME.teal },
        },
        {
          name: '丢包率',
          type: 'bar',
          yAxisIndex: 1,
          barWidth: 8,
          data: series.map((p) => p.lossPct),
          itemStyle: { color: 'rgba(255, 82, 82, 0.65)', borderRadius: [3, 3, 0, 0] },
        },
      ],
    }),
    [series],
  )

  const { elRef } = useEchart(options)

  return (
    <ItemWrap title="丢包率与健康" className="ms-loss-health-panel">
      <div ref={elRef} className="ms-chart-fill" />
    </ItemWrap>
  )
}
