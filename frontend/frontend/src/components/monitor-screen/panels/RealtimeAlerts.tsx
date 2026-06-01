import { useEffect, useRef } from 'react'
import ItemWrap from '../ItemWrap'
import { RULE_ALARM_STATIC, type RuleAlarmItem } from '../monitorScreenApi'

function levelClass(level: string) {
  if (level === '严重') return 'critical'
  if (level === '警告') return 'warn'
  return 'info'
}

function Row({ item, index }: { item: RuleAlarmItem; index: number }) {
  return (
    <div className="ms-list-item ms-list-item--right">
      <span className="ms-list-item__order">{index + 1}</span>
      <div className="ms-list-item__body ms-list-item__body--wide">
        <div className="ms-list-item__line" />
        <div className="ms-list-item__row">
          <div className="ms-list-item__info">
            <span className="ms-list-item__label">时间：</span>
            <span className="ms-list-item__sub">{item.time}</span>
          </div>
          <div className="ms-list-item__info">
            <span className="ms-list-item__label">类型：</span>
            <span className="ms-list-item__primary">{item.type}</span>
          </div>
          <div className="ms-list-item__info">
            <span className="ms-list-item__label">级别：</span>
            <span className={`ms-alarm-level ms-alarm-level--${levelClass(item.level)}`}>
              {item.level}
            </span>
          </div>
        </div>
        <div className="ms-list-item__info ms-list-item__info--full">
          <span className="ms-list-item__label">告警内容：</span>
          <span className="ms-list-item__sub">{item.content}</span>
        </div>
      </div>
    </div>
  )
}

const PAUSE_BOTTOM_MS = 1200
const SCROLL_STEP = 0.5

export default function RealtimeAlerts() {
  const viewportRef = useRef<HTMLDivElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)
  const blockRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const viewport = viewportRef.current
    const track = trackRef.current
    const block = blockRef.current
    if (!viewport || !track || !block) return

    let y = 0
    let raf = 0
    let pauseUntil = 0
    let phase: 'scroll' | 'pause-bottom' = 'scroll'

    const maxScroll = () => Math.max(0, block.offsetHeight - viewport.clientHeight)

    const step = (ts: number) => {
      const max = maxScroll()

      if (max <= 0) {
        y = 0
        phase = 'scroll'
        track.style.transform = ''
        raf = requestAnimationFrame(step)
        return
      }

      if (phase === 'pause-bottom') {
        if (ts < pauseUntil) {
          raf = requestAnimationFrame(step)
          return
        }
        y = 0
        phase = 'scroll'
        track.style.transform = 'translateY(0)'
        raf = requestAnimationFrame(step)
        return
      }

      y += SCROLL_STEP
      if (y >= max) {
        y = max
        track.style.transform = `translateY(-${y}px)`
        phase = 'pause-bottom'
        pauseUntil = ts + PAUSE_BOTTOM_MS
      } else {
        track.style.transform = `translateY(-${y}px)`
      }

      raf = requestAnimationFrame(step)
    }

    const remeasure = () => {
      const max = maxScroll()
      if (y > max) {
        y = 0
        phase = 'scroll'
        track.style.transform = 'translateY(0)'
      }
    }

    raf = requestAnimationFrame(step)
    const ro = new ResizeObserver(remeasure)
    ro.observe(viewport)
    ro.observe(block)
    window.addEventListener('resize', remeasure)

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('resize', remeasure)
      track.style.transform = ''
    }
  }, [])

  return (
    <ItemWrap
      title="规则告警表"
      className="ms-alarm-list-panel"
      contentClassName="ms-alarm-list-panel__body"
    >
      <div ref={viewportRef} className="ms-alarm-scroll-viewport">
        <div ref={trackRef} className="ms-alarm-scroll-track">
          <div ref={blockRef} className="ms-alarm-scroll-block">
            {RULE_ALARM_STATIC.map((item, i) => (
              <Row key={`${item.content}-${i}`} item={item} index={i} />
            ))}
          </div>
        </div>
      </div>
    </ItemWrap>
  )
}
