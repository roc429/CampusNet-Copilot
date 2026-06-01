import { useEffect, useRef, useState, type ReactNode } from 'react'

type Props = {
  width?: number
  height?: number
  /**
   * contain：完整显示（可能留白）
   * cover：等比铺满（可能裁切）
   * stretch：宽高独立缩放
   * fill：等比缩放 + 动态画布高度，铺满宽高且不变形
   */
  fit?: 'contain' | 'cover' | 'stretch' | 'fill'
  /** 垂直对齐（fill 模式固定贴顶） */
  align?: 'center' | 'top' | 'bottom'
  safeInset?: number
  children: ReactNode
}

const ALIGN_ORIGIN = {
  center: 'center center',
  top: 'top center',
  bottom: 'bottom center',
} as const

/**
 * 大屏缩放：fill 模式下按宽度等比缩放，并动态调整画布高度以铺满视口
 */
export default function ScaleScreen({
  width = 1920,
  height = 1080,
  fit = 'contain',
  align = 'center',
  safeInset = 1,
  children,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState({ x: 1, y: 1 })
  const [canvasHeight, setCanvasHeight] = useState(height)

  const effectiveAlign = fit === 'fill' ? 'top' : align

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const resize = () => {
      const w = host.clientWidth
      const h = host.clientHeight
      if (w <= 0 || h <= 0) return

      const sx = w / width
      const sy = h / height

      if (fit === 'fill') {
        const s = sx * safeInset
        setScale({ x: s, y: s })
        setCanvasHeight(h / s)
      } else if (fit === 'stretch') {
        setScale({ x: sx, y: sy })
        setCanvasHeight(height)
      } else if (fit === 'cover') {
        const s = Math.max(sx, sy)
        setScale({ x: s, y: s })
        setCanvasHeight(height)
      } else {
        const s = (sx <= sy ? sx : Math.min(sx, sy)) * safeInset
        setScale({ x: s, y: s })
        setCanvasHeight(height)
      }

      requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
    }

    resize()
    const raf = requestAnimationFrame(resize)

    const ro = new ResizeObserver(() => resize())
    ro.observe(host)
    window.addEventListener('resize', resize)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('resize', resize)
    }
  }, [width, height, fit, safeInset])

  return (
    <div
      className={`ms-scale-host ms-scale-host--align-${effectiveAlign}`}
      ref={hostRef}
    >
      <div
        className="ms-scale-inner"
        style={{
          width: `${width}px`,
          height: `${canvasHeight}px`,
          transform: `scale(${scale.x}, ${scale.y})`,
          transformOrigin: ALIGN_ORIGIN[effectiveAlign],
        }}
      >
        {children}
      </div>
    </div>
  )
}
