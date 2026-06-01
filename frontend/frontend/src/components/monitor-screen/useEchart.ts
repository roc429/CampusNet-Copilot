import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

/** 大屏 ScaleScreen 使用 CSS transform 缩放时，修正 ECharts 滑块拖拽坐标（ECharts 6 可能无此内部 API） */
function patchPointerForCssScale(chart: echarts.ECharts, el: HTMLElement): boolean {
  const zr = chart.getZr()
  const handler = zr.handler as unknown as {
    normalize?: (event: unknown, origin?: unknown) => { zrX: number; zrY: number }
  }
  const rawNormalize = handler.normalize
  if (typeof rawNormalize !== 'function') {
    return false
  }

  handler.normalize = (event, origin) => {
    const result = rawNormalize.call(handler, event, origin)
    const rect = el.getBoundingClientRect()
    const scaleX = el.offsetWidth > 0 ? rect.width / el.offsetWidth : 1
    const scaleY = el.offsetHeight > 0 ? rect.height / el.offsetHeight : 1
    if (Math.abs(scaleX - 1) > 0.001 || Math.abs(scaleY - 1) > 0.001) {
      result.zrX /= scaleX
      result.zrY /= scaleY
    }
    return result
  }
  return true
}

export function useEchart(options: EChartsOption | null) {
  const elRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const patchedRef = useRef(false)
  const optionsRef = useRef(options)
  optionsRef.current = options

  useEffect(() => {
    const el = elRef.current
    if (!el || !options) return

    let cancelled = false

    const applyOption = () => {
      if (cancelled || !elRef.current || !optionsRef.current) return

      const { offsetWidth, offsetHeight } = elRef.current
      if (offsetWidth <= 0 || offsetHeight <= 0) return

      if (!chartRef.current || chartRef.current.isDisposed()) {
        chartRef.current = echarts.init(elRef.current, undefined, { renderer: 'canvas' })
        patchedRef.current = false
      }

      if (!patchedRef.current && chartRef.current) {
        void patchPointerForCssScale(chartRef.current, elRef.current)
        patchedRef.current = true
      }

      chartRef.current.setOption(optionsRef.current, { notMerge: true })
      chartRef.current.resize()
    }

    const resizeOnly = () => {
      if (cancelled || !chartRef.current || chartRef.current.isDisposed()) return
      chartRef.current.resize()
    }

    const ro = new ResizeObserver(resizeOnly)
    ro.observe(el)

    applyOption()
    const raf = requestAnimationFrame(applyOption)

    const onWindowResize = () => resizeOnly()
    window.addEventListener('resize', onWindowResize)

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('resize', onWindowResize)
    }
  }, [options])

  useEffect(() => {
    return () => {
      chartRef.current?.dispose()
      chartRef.current = null
      patchedRef.current = false
    }
  }, [])

  return { elRef, chart: chartRef }
}
