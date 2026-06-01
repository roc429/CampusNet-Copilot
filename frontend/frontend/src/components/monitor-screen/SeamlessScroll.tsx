import { useEffect, useRef, useState, type ReactNode } from 'react'

type Props = {
  children: ReactNode
  enabled?: boolean
  /** 内容未测出溢出时也强制滚动（用于固定条数轮播） */
  forceScroll?: boolean
  className?: string
}

/** 列表无缝滚动：内容超出容器时才滚动，并复制一份实现无缝循环 */
export default function SeamlessScroll({
  children,
  enabled = true,
  forceScroll = false,
  className = '',
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)
  const blockRef = useRef<HTMLDivElement>(null)
  const [shouldScroll, setShouldScroll] = useState(forceScroll)

  useEffect(() => {
    const host = hostRef.current
    const block = blockRef.current
    if (!host || !block || !enabled) {
      setShouldScroll(false)
      return
    }

    const measure = () => {
      requestAnimationFrame(() => {
        const hostEl = hostRef.current
        const blockEl = blockRef.current
        if (!hostEl || !blockEl) return
        const overflow = blockEl.offsetHeight > hostEl.clientHeight + 4
        setShouldScroll(Boolean(forceScroll) || overflow)
      })
    }

    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(host)
    ro.observe(block)
    window.addEventListener('resize', measure)

    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [enabled, children, forceScroll])

  useEffect(() => {
    const track = trackRef.current
    if (!track) return

    if (!shouldScroll) {
      track.style.transform = ''
      return
    }

    let y = 0
    let raf = 0

    const blockHeight = () => blockRef.current?.offsetHeight ?? 0

    const step = () => {
      const limit = blockHeight()
      if (limit <= 0) {
        raf = requestAnimationFrame(step)
        return
      }
      y += 0.5
      if (y >= limit) y = 0
      track.style.transform = `translateY(-${y}px)`
      raf = requestAnimationFrame(step)
    }

    raf = requestAnimationFrame(step)
    return () => {
      cancelAnimationFrame(raf)
      track.style.transform = ''
    }
  }, [shouldScroll, children])

  return (
    <div ref={hostRef} className={`ms-seamless ${className}`.trim()}>
      <div ref={trackRef} className="ms-seamless__track">
        <div ref={blockRef} className="ms-seamless__block">
          {children}
        </div>
        {shouldScroll ? (
          <div className="ms-seamless__block" aria-hidden="true">
            {children}
          </div>
        ) : null}
      </div>
    </div>
  )
}
