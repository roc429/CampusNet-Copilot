import { useCallback, useEffect, useState } from 'react'
import ItemWrap from '../ItemWrap'
import { fetchApStatusList, type ApStatusItem } from '../monitorScreenApi'

function loadTone(loadPct: number, online: boolean) {
  if (!online) return 'off'
  if (loadPct >= 15) return 'high'
  if (loadPct >= 8) return 'mid'
  return 'ok'
}

export default function AlarmTrend() {
  const [items, setItems] = useState<ApStatusItem[]>([])

  const load = useCallback(async () => {
    const res = await fetchApStatusList()
    if (res.success) setItems(res.data)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <ItemWrap title="12路AP状态一览" className="ms-ap-panel">
      <div className="ms-ap-grid">
        {items.map((ap) => {
          const tone = loadTone(ap.loadPct, ap.online)
          return (
            <div key={ap.id} className={`ms-ap-card ms-ap-card--${tone}`}>
              <div className="ms-ap-card__id">{ap.id}</div>
              <div className={`ms-ap-card__dot ms-ap-card__dot--${tone}`} />
              <div className="ms-ap-card__status">{ap.online ? '在线' : '离线'}</div>
              <div className="ms-ap-card__role">{ap.role}</div>
              <div className="ms-ap-card__metric">
                {ap.online ? `${ap.loadPct.toFixed(1)}%` : '--'}
              </div>
              <div className="ms-ap-card__sub">
                {ap.online ? `SW${ap.dpid}` : '未接入'}
              </div>
            </div>
          )
        })}
      </div>
    </ItemWrap>
  )
}
