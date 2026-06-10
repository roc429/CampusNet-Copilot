import { useEffect, useMemo, useRef, useState } from 'react'

import { Clock, FileBarChart, Files, RefreshCw, Trash2 } from 'lucide-react'

import {
  fetchAdminEvents,
  fetchRemoteAgentStatus,
  fetchRemoteReport,
  type AdminEvent,
} from '../api/agentApi'

import DiagnosisReportCard from './DiagnosisReportCard'

import { shortEventId } from './reportParser'

import './ReportCenterPanel.css'



const STORAGE_KEY = 'campusnet_reports'



type StoredReport = {
  eventId: string
  question: string
  savedAt: number
}

type ReportListItem = {
  eventId: string
  question: string
  savedAt: number | null
  status?: string
  source: 'api' | 'local'
}



function loadStored(): StoredReport[] {

  try {

    const raw = localStorage.getItem(STORAGE_KEY)

    if (!raw) {

      return []

    }

    const parsed = JSON.parse(raw) as StoredReport[]

    return Array.isArray(parsed) ? parsed : []

  } catch {

    return []

  }

}



function saveStored(items: StoredReport[]) {

  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, 20)))

}



function removeStored(eventId: string): StoredReport[] {

  const next = loadStored().filter((x) => x.eventId !== eventId)

  saveStored(next)

  return next

}



function mapApiEvent(event: AdminEvent): ReportListItem {
  const question =
    event.question?.trim() ||
    (event.device_id ? `${event.device_id} 相关诊断` : '') ||
    (event.event_type === 'user_diagnosis_request' ? '用户诊断请求' : event.event_type) ||
    '运维事件'
  const parsed = event.timestamp ? Date.parse(event.timestamp) : Number.NaN
  return {
    eventId: event.event_id,
    question,
    savedAt: Number.isFinite(parsed) ? parsed : null,
    status: event.status,
    source: 'api',
  }
}

function mergeReportItems(apiItems: ReportListItem[], localItems: StoredReport[]): ReportListItem[] {
  const seen = new Set<string>()
  const merged: ReportListItem[] = []

  for (const item of apiItems) {
    if (seen.has(item.eventId)) continue
    seen.add(item.eventId)
    merged.push(item)
  }

  for (const item of localItems) {
    if (seen.has(item.eventId)) continue
    seen.add(item.eventId)
    merged.push({
      eventId: item.eventId,
      question: item.question,
      savedAt: item.savedAt,
      source: 'local',
    })
  }

  return merged
}

function formatListTime(ts: number): string {

  const d = new Date(ts)

  const now = new Date()

  const sameDay =

    d.getFullYear() === now.getFullYear() &&

    d.getMonth() === now.getMonth() &&

    d.getDate() === now.getDate()

  if (sameDay) {

    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })

  }

  return d.toLocaleString('zh-CN', {

    month: 'numeric',

    day: 'numeric',

    hour: '2-digit',

    minute: '2-digit',

    hour12: false,

  })

}



type Props = {

  /** 从 AI 助手跳转时可预选 event_id */

  initialEventId?: string | null

}



export default function ReportCenterPanel({ initialEventId }: Props) {

  const listRef = useRef<HTMLDivElement>(null)

  const [items, setItems] = useState<ReportListItem[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(initialEventId ?? null)

  const [reportText, setReportText] = useState<string | null>(null)

  const [loading, setLoading] = useState(false)

  const [error, setError] = useState<string | null>(null)



  const selectedItem = useMemo(

    () => items.find((item) => item.eventId === selectedId) ?? null,

    [items, selectedId],

  )



  const loadList = async () => {
    setListLoading(true)
    setListError(null)
    try {
      const events = await fetchAdminEvents()
      setItems(mergeReportItems(events.map(mapApiEvent), loadStored()))
    } catch (e) {
      setListError(e instanceof Error ? e.message : '列表加载失败')
      setItems(mergeReportItems([], loadStored()))
    } finally {
      setListLoading(false)
    }
  }

  useEffect(() => {
    void loadList()
  }, [])

  useEffect(() => {
    if (initialEventId) {
      setSelectedId(initialEventId)
    }
  }, [initialEventId])

  useEffect(() => {

    if (!selectedId) {

      setReportText(null)

      return

    }

    let cancelled = false

    setLoading(true)

    setError(null)

    void (async () => {

      try {

        try {
          const report = await fetchRemoteReport(selectedId)
          if (cancelled) return
          setReportText(report.report_text)
          return
        } catch {
          /* 报告可能尚未生成，继续查状态 */
        }

        const status = await fetchRemoteAgentStatus(selectedId)
        if (cancelled) return

        if (status.report_text) {
          setReportText(status.report_text)
          return
        }

        if (status.report_ready) {
          const report = await fetchRemoteReport(selectedId)
          if (!cancelled) setReportText(report.report_text)
          return
        }

        setReportText(null)
        setError('报告仍在生成中，请稍后刷新')

      } catch (e) {

        if (!cancelled) {

          setError(e instanceof Error ? e.message : '加载失败')

          setReportText(null)

        }

      } finally {

        if (!cancelled) {

          setLoading(false)

        }

      }

    })()

    return () => {

      cancelled = true

    }

  }, [selectedId])



  function handleRefreshList() {
    void loadList()
  }

  function handleDelete(eventId: string) {
    removeStored(eventId)
    setItems((prev) => prev.filter((x) => !(x.eventId === eventId && x.source === 'local')))
    if (selectedId === eventId) {
      setSelectedId(null)
      setReportText(null)
      setError(null)
    }
  }



  function handleScrollListEnd() {

    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })

  }



  return (
    <div className="report-center">
      <div className="report-center__shell">
        <header className="report-center__header">

        <div className="report-center__header-main">

          <h1 className="report-center__title">报告中心</h1>

          <p className="report-center__desc">

            智能诊断任务生成的运维报告

            <span className="report-center__desc-dot">·</span>

            ECS 事件列表

          </p>

        </div>

        <div className="report-center__header-actions">

          <span className="report-center__count">

            <Files size={15} aria-hidden="true" />

            {items.length} 份报告

          </span>

          <button type="button" className="report-center__refresh" onClick={handleRefreshList}>

            <RefreshCw size={14} aria-hidden="true" />

            刷新列表

          </button>

        </div>

      </header>



      <div className="report-center__layout">

        <aside className="report-center__list-panel">

          <div className="report-center__list-head">

            <Clock size={16} className="report-center__list-head-icon" aria-hidden="true" />

            历史诊断

          </div>

          <div className="report-center__list" ref={listRef}>

            {listLoading ? (
              <div className="report-center__empty">
                <p className="report-center__empty-title">加载事件列表…</p>
              </div>
            ) : items.length === 0 ? (
              <div className="report-center__empty">
                <div className="report-center__empty-icon" aria-hidden="true">
                  <FileBarChart size={28} strokeWidth={1.5} />
                </div>
                <p className="report-center__empty-title">暂无报告</p>
                <p className="report-center__empty-desc">
                  {listError ?? '在 AI 助手开启「智能诊断」提问后，完成的报告会出现在这里。'}
                </p>
              </div>
            ) : (

              items.map((item) => (

                <div

                  key={item.eventId}

                  className={

                    selectedId === item.eventId

                      ? 'report-center__item report-center__item--active'

                      : 'report-center__item'

                  }

                >

                  <button

                    type="button"

                    className="report-center__item-main"

                    onClick={() => setSelectedId(item.eventId)}

                  >

                    <span className="report-center__item-dot" aria-hidden="true" />

                    <span className="report-center__item-body">

                      <span className="report-center__item-q">{item.question}</span>

                      <span className="report-center__item-meta">

                        <span className="report-center__item-id" title={item.eventId}>

                          {shortEventId(item.eventId)}

                        </span>

                        <span className="report-center__item-time">
                          {item.savedAt != null
                            ? formatListTime(item.savedAt)
                            : item.status === 'completed'
                              ? '已完成'
                              : (item.status ?? '进行中')}
                        </span>

                      </span>

                    </span>

                  </button>

                  {item.source === 'local' ? (
                    <button
                      type="button"
                      className="report-center__item-delete"
                      title="从列表移除"
                      aria-label="从列表移除"
                      onClick={() => handleDelete(item.eventId)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  ) : null}

                </div>

              ))

            )}

          </div>

          {items.length > 0 ? (

            <div className="report-center__list-footer">

              <button type="button" className="report-center__list-more" onClick={handleScrollListEnd}>

                查看更多历史 &gt;

              </button>

            </div>

          ) : null}

        </aside>



        <main className="report-center__main">

          {!selectedId ? (

            <div className="report-center__placeholder">

              <FileBarChart size={40} strokeWidth={1.25} className="report-center__placeholder-icon" />

              <p>选择左侧报告查看详情</p>

            </div>

          ) : loading ? (

            <div className="report-center__loading">

              <div className="report-center__loading-bar" />

              <div className="report-center__loading-bar report-center__loading-bar--short" />

              <div className="report-center__loading-bar report-center__loading-bar--medium" />

              <p>正在加载报告…</p>

            </div>

          ) : error && !reportText ? (

            <div className="report-center__error">

              <p className="report-center__error-title">暂时无法加载</p>

              <p>{error}</p>

            </div>

          ) : reportText ? (

            <DiagnosisReportCard

              eventId={selectedId}

              reportText={reportText}

              question={selectedItem?.question}

              variant="center"

            />

          ) : (

            <div className="report-center__placeholder">

              <p>{error ?? '暂无报告内容'}</p>

            </div>

          )}

        </main>
      </div>
      </div>
    </div>
  )

}



export function persistReport(eventId: string, question: string) {
  const items = loadStored().filter((x) => x.eventId !== eventId)
  items.unshift({ eventId, question, savedAt: Date.now() })
  saveStored(items)
}

