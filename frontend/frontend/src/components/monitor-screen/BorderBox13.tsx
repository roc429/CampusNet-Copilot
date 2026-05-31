import { useEffect, useRef, useState, type ReactNode } from 'react'

/** 与 @jiaminghi/data-view 的 dv-border-box-13 一致 */
const COLORS = ['#1890FF', '#4DB6AC'] as const
const STROKE_WIDTH = 3
const STROKE_DASH = 5

function buildPaths(w: number, h: number) {
  return {
    fill: `M 5 20 L 5 10 L 12 3  L 60 3 L 68 10 L ${w - 20} 10 L ${w - 5} 25 L ${w - 5} ${h - 5} L 20 ${h - 5} L 5 ${h - 20} L 5 20`,
    dash: 'M 16 9 L 61 9',
    corner1: 'M 5 20 L 5 10 L 12 3  L 60 3 L 68 10',
    corner2: `M ${w - 5} ${h - 30} L ${w - 5} ${h - 5} L ${w - 30} ${h - 5}`,
  }
}

type Props = {
  children: ReactNode
  className?: string
}

export default function BorderBox13({ children, className = '' }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 200, h: 120 })

  useEffect(() => {
    const el = ref.current
    if (!el) return

    /** 与 DataV autoResize 一致：用 clientWidth/Height，避免 scale 变换下 getBoundingClientRect 偏小 */
    const update = () => {
      setSize({
        w: Math.max(1, el.clientWidth),
        h: Math.max(1, el.clientHeight),
      })
    }

    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    window.addEventListener('resize', update)

    return () => {
      ro.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [])

  const paths = buildPaths(size.w, size.h)

  return (
    <div ref={ref} className={`dv-border-box-13 ${className}`.trim()}>
      <svg
        className="dv-border-svg-container"
        width={size.w}
        height={size.h}
        viewBox={`0 0 ${size.w} ${size.h}`}
      >
        <path
          fill="transparent"
          stroke={COLORS[0]}
          strokeWidth={STROKE_WIDTH}
          strokeLinejoin="round"
          d={paths.fill}
        />
        <path
          fill="transparent"
          strokeWidth={STROKE_DASH}
          strokeLinecap="round"
          strokeDasharray="10, 5"
          stroke={COLORS[0]}
          d={paths.dash}
        />
        <path
          fill="transparent"
          stroke={COLORS[1]}
          strokeWidth={STROKE_WIDTH}
          strokeLinejoin="round"
          d={paths.corner1}
        />
        <path
          fill="transparent"
          stroke={COLORS[1]}
          strokeWidth={STROKE_WIDTH}
          strokeLinejoin="round"
          d={paths.corner2}
        />
      </svg>
      <div className="border-box-content">{children}</div>
    </div>
  )
}
