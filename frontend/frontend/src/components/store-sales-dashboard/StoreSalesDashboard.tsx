import { useEffect, useMemo, useRef, useState } from 'react'
import type { EChartsOption } from 'echarts'
import { useEchart } from '../monitor-screen/useEchart'
import {
  buildCapacityGaugeOption,
  buildHorizonQuantileOption,
  buildHourlyBarOption,
  buildPredictionForecastOptionFromLive,
  buildRoleForecastOptionFromLive,
  buildRolePieOption,
  type LiveForecastSeries,
  type LiveRoleSeries,
} from './predictionCharts'
import { callMcpTool, extractMcpStructured } from '../../api/agentApi'
import ssdHeaderBg from '../../assets/header.png'
import { PREDICTION_STATIC, type HorizonKey } from './predictionStaticData'
import './icomoon.css'
import './StoreSalesDashboard.css'

type MonitorRow = { time: string; address: string; code: string }

function MarqueeRows({ rows }: { rows: readonly MonitorRow[] }) {
  const doubled = useMemo(() => [...rows, ...rows], [rows])
  return (
    <div className="marquee-view">
      <div className="marquee">
        {doubled.map((row, i) => (
          <div className="row" key={`${row.code}-${i}`}>
            <span className="col">{row.time}</span>
            <span className="col">{row.address}</span>
            <span className="col">{row.code}</span>
            <span className="icon-dot" />
          </div>
        ))}
      </div>
    </div>
  )
}

function ChartBox({ options }: { options: EChartsOption | null }) {
  const { elRef } = useEchart(options)
  return <div ref={elRef} style={{ width: '100%', height: '100%' }} />
}

const P = PREDICTION_STATIC
const HORIZON_KEYS = P.horizonKeys

const LIVE_DEVICE_ID = 'AP-EXAM-301'
const LIVE_METRIC = 'packet_loss'
const LIVE_HORIZON_MINUTES = 30
const LIVE_FREQ = '5m'
const LIVE_STEP_MINUTES = 5

const ROLE_FORECAST_TARGETS = [
  { name: '教学区AP', deviceId: 'AP-EXAM-301', color: '#1890ff' },
  { name: '宿舍区AP', deviceId: 'AP-DORM-A1', color: '#52c41a' },
  { name: '数据接入', deviceId: 'OF-CORE-01', color: '#faad14' },
] as const
const ROLE_HORIZON_MINUTES = 21 * 60
const ROLE_FREQ = '60m'
const ROLE_METRIC = 'cpu_load'

function parseQuantileSeries(quantiles: Record<string, unknown> | undefined) {
  const pick = (keys: string[]) => {
    if (!quantiles) return [] as number[]
    for (const key of keys) {
      const arr = quantiles[key]
      if (Array.isArray(arr) && arr.length > 0) {
        return arr.map((v) => Number(v))
      }
    }
    return [] as number[]
  }
  return {
    q10: pick(['0.10', '0.1']),
    q50: pick(['0.50', '0.5']),
    q90: pick(['0.90', '0.9']),
  }
}

function buildLiveLabels(count: number, stepMinutes: number): string[] {
  return Array.from({ length: count }, (_, i) => `T+${(i + 1) * stepMinutes}m`)
}

function buildHourlyLabels(count: number): string[] {
  return Array.from({ length: count }, (_, i) => `T+${i + 1}h`)
}

function isValidForecastPayload(structured: Record<string, unknown>): boolean {
  const forecast = (structured.forecast as number[] | undefined) ?? []
  if (forecast.length === 0) return false
  const source = String(structured.source ?? 'timesfm')
  if (source === 'local-empty' && forecast.every((v) => Number(v) === 0)) return false
  return true
}

export default function StoreSalesDashboard() {
  const hostRef = useRef<HTMLDivElement>(null)
  const [monitorTab, setMonitorTab] = useState(0)
  const [horizonKey, setHorizonKey] = useState<HorizonKey>('all')
  const [portIdx, setPortIdx] = useState(0)
  const [liveForecastOption, setLiveForecastOption] = useState<EChartsOption | null>(null)
  const [liveSource, setLiveSource] = useState<string | null>(null)
  const [liveForecastLoading, setLiveForecastLoading] = useState(true)
  const [roleForecastOption, setRoleForecastOption] = useState<EChartsOption | null>(null)
  const [roleForecastLoading, setRoleForecastLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setLiveForecastLoading(true)
      try {
        const resp = await callMcpTool('timesfm', 'forecast_metric', {
          device_id: LIVE_DEVICE_ID,
          metric: LIVE_METRIC,
          horizon_minutes: LIVE_HORIZON_MINUTES,
          freq: LIVE_FREQ,
        })
        if (cancelled) return

        const structured = extractMcpStructured(resp)
        if (!isValidForecastPayload(structured)) return

        const forecast = structured.forecast as number[]
        const source = String(structured.source ?? 'timesfm')

        const freqMatch = String(structured.freq ?? LIVE_FREQ).match(/^(\d+)m$/i)
        const stepMinutes = freqMatch ? Number(freqMatch[1]) : LIVE_STEP_MINUTES
        const { q10, q50, q90 } = parseQuantileSeries(
          structured.quantiles as Record<string, unknown> | undefined,
        )
        const q50Line = q50.length === forecast.length ? q50 : forecast
        const q10Line =
          q10.length === forecast.length ? q10 : forecast.map((v) => Number(v) * 0.85)
        const q90Line =
          q90.length === forecast.length ? q90 : forecast.map((v) => Number(v) * 1.15)

        const liveSeries: LiveForecastSeries = {
          labels: buildLiveLabels(forecast.length, stepMinutes),
          q10: q10Line,
          q50: q50Line,
          q90: q90Line,
        }

        setLiveSource(source)
        setLiveForecastOption(buildPredictionForecastOptionFromLive(liveSeries))
      } catch {
        /* MCP 不可用时留空，不展示静态图 */
      } finally {
        if (!cancelled) setLiveForecastLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setRoleForecastLoading(true)
      try {
        const results = await Promise.all(
          ROLE_FORECAST_TARGETS.map(async (role) => {
            try {
              const resp = await callMcpTool('timesfm', 'forecast_metric', {
                device_id: role.deviceId,
                metric: ROLE_METRIC,
                horizon_minutes: ROLE_HORIZON_MINUTES,
                freq: ROLE_FREQ,
              })
              const structured = extractMcpStructured(resp)
              if (!isValidForecastPayload(structured)) return null
              const { q50 } = parseQuantileSeries(
                structured.quantiles as Record<string, unknown> | undefined,
              )
              const forecast = structured.forecast as number[]
              const q50Line = q50.length === forecast.length ? q50 : forecast
              return {
                name: role.name,
                color: role.color,
                q50: q50Line,
              } satisfies LiveRoleSeries
            } catch {
              return null
            }
          }),
        )
        if (cancelled) return

        const roles = results.filter((r): r is LiveRoleSeries => r != null)
        if (roles.length === 0) return

        const pointCount = Math.min(...roles.map((r) => r.q50.length))
        if (pointCount === 0) return

        const aligned = roles.map((r) => ({
          ...r,
          q50: r.q50.slice(0, pointCount),
        }))

        setRoleForecastOption(
          buildRoleForecastOptionFromLive(buildHourlyLabels(pointCount), aligned),
        )
      } catch {
        /* MCP 不可用时留空，不展示静态图 */
      } finally {
        if (!cancelled) setRoleForecastLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const html = document.documentElement
    const prev = html.style.fontSize
    const setFont = () => {
      const host = hostRef.current
      if (!host) return
      const w = host.clientWidth
      const h = host.clientHeight
      let width = w
      if (width < 1024) width = 1024
      if (width > 1920) width = 1920
      const scaleW = width / 80
      const scaleH = h / 44.5
      html.style.fontSize = `${Math.min(scaleW, scaleH)}px`
      requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
    }
    setFont()
    const ro = hostRef.current ? new ResizeObserver(setFont) : null
    ro?.observe(hostRef.current!)
    window.addEventListener('resize', setFont)
    return () => {
      ro?.disconnect()
      window.removeEventListener('resize', setFont)
      html.style.fontSize = prev
    }
  }, [])

  useEffect(() => {
    const id = window.setInterval(() => {
      setHorizonKey((k) => {
        const i = HORIZON_KEYS.indexOf(k)
        return HORIZON_KEYS[(i + 1) % HORIZON_KEYS.length]
      })
    }, 3000)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    const id = window.setInterval(() => {
      setPortIdx((i) => (i + 1) % P.portRankings.length)
    }, 2000)
    return () => window.clearInterval(id)
  }, [])

  const rolePieOption = useMemo(() => buildRolePieOption(), [])
  const hourlyBarOption = useMemo(() => buildHourlyBarOption(), [])
  const quantileOption = useMemo(() => buildHorizonQuantileOption(horizonKey), [horizonKey])
  const gaugeOption = useMemo(() => buildCapacityGaugeOption(), [])

  const horizon = P.horizonStats[horizonKey]
  const activePort = P.portRankings[portIdx]
  const portSubList = activePort?.hourTop ?? []

  return (
    <div className="ssd-page-host" ref={hostRef}>
      <div className="ssd-page">
        <header className="ssd-banner">
          <img className="ssd-banner__img" src={ssdHeaderBg} alt="" />
          <h1 className="ssd-banner__title">
            <span className="ssd-banner__title-en">TimesFM</span>
            <span className="ssd-banner__title-zh">预测看板</span>
          </h1>
        </header>
        <div className="ssd-viewport">
          {/* 左列 */}
          <div className="column">
            <div className="overview panel">
              <div className="inner">
                {P.overviewStats.map((s) => (
                  <div className="item" key={s.label}>
                    <h4>{s.value}</h4>
                    <span>
                      <i className="icon-dot" style={{ color: s.color }} />
                      {s.label}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="monitor panel">
              <div className="inner">
                <div className="tabs">
                  <a
                    className={monitorTab === 0 ? 'active' : ''}
                    onClick={() => setMonitorTab(0)}
                  >
                    风险预测监控
                  </a>
                  <a
                    className={monitorTab === 1 ? 'active' : ''}
                    onClick={() => setMonitorTab(1)}
                  >
                    置信区间告警
                  </a>
                </div>
                <div className={`content ${monitorTab === 0 ? 'is-active' : ''}`}>
                  <div className="head">
                    <span className="col">预测时间</span>
                    <span className="col">端口/角色</span>
                    <span className="col">风险信息</span>
                  </div>
                  <MarqueeRows rows={P.riskMonitorRows} />
                </div>
                <div className={`content ${monitorTab === 1 ? 'is-active' : ''}`}>
                  <div className="head">
                    <span className="col">预测时间</span>
                    <span className="col">端口/角色</span>
                    <span className="col">告警信息</span>
                  </div>
                  <MarqueeRows rows={P.exceedCiRows} />
                </div>
              </div>
            </div>

            <div className="point panel">
              <div className="inner">
                <h3>角色负载分布</h3>
                <div className="chart">
                  <div className="pie">
                    <ChartBox options={rolePieOption} />
                  </div>
                  <div className="data">
                    <div className="item">
                      <h4>{P.kpi.portCount}</h4>
                      <span>
                        <i className="icon-dot" style={{ color: '#ed3f35' }} />
                        监控端口
                      </span>
                    </div>
                    <div className="item">
                      <h4>{P.meta.snapshotCount}</h4>
                      <span>
                        <i className="icon-dot" style={{ color: '#eacf19' }} />
                        预测快照
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 中列 */}
          <div className="column">
            <div className="map panel">
              <div className="inner">
                <h3>
                  <span className="icon-cube" />
                  TimesFM 负载预测
                  {liveSource ? (
                    <small style={{ marginLeft: 8, fontSize: '0.55em', color: '#6acca3' }}>
                      实时 · {liveSource}
                    </small>
                  ) : null}
                </h3>
                <div className="chart prediction-chart">
                  {liveForecastOption ? (
                    <ChartBox options={liveForecastOption} />
                  ) : (
                    <div className="prediction-chart__empty">
                      {liveForecastLoading ? '预测数据加载中…' : '暂无 TimesFM 预测数据'}
                    </div>
                  )}
                </div>
                <div className="chart prediction-chart prediction-chart--role">
                  {roleForecastOption ? (
                    <ChartBox options={roleForecastOption} />
                  ) : (
                    <div className="prediction-chart__empty">
                      {roleForecastLoading ? '分区预测加载中…' : '暂无分区预测数据'}
                    </div>
                  )}
                </div>
                <p className="prediction-note">{P.capacity.recommendation}</p>
              </div>
            </div>

            <div className="users panel">
              <div className="inner">
                <h3>分时段预测负载</h3>
                <div className="chart">
                  <div className="bar">
                    <ChartBox options={hourlyBarOption} />
                  </div>
                  <div className="data">
                    <div className="item">
                      <h4>{P.meta.horizonHours}h</h4>
                      <span>
                        <i className="icon-dot" style={{ color: '#ed3f35' }} />
                        预测窗口
                      </span>
                    </div>
                    <div className="item">
                      <h4>{P.meta.rowCount}</h4>
                      <span>
                        <i className="icon-dot" style={{ color: '#eacf19' }} />
                        预测记录
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 右列 */}
          <div className="column">
            <div className="order panel">
              <div className="inner">
                <div className="filter">
                  {HORIZON_KEYS.map((key) => (
                    <a
                      key={key}
                      className={horizonKey === key ? 'active' : ''}
                      onClick={() => setHorizonKey(key)}
                    >
                      {P.horizonLabels[key]}
                    </a>
                  ))}
                </div>
                <div className="data">
                  <div className="item">
                    <h4>{horizon.avgQ50}%</h4>
                    <span>
                      <i className="icon-dot" style={{ color: '#ed3f35' }} />
                      平均 Q50
                    </span>
                  </div>
                  <div className="item">
                    <h4>{horizon.maxQ90}%</h4>
                    <span>
                      <i className="icon-dot" style={{ color: '#eacf19' }} />
                      最大 Q90
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="sales panel">
              <div className="inner">
                <div className="caption">
                  <h3>分位预测曲线</h3>
                  <span className="ssd-caption-tag">{P.horizonLabels[horizonKey]}</span>
                </div>
                <div className="chart">
                  <div className="line">
                    <ChartBox options={quantileOption} />
                  </div>
                </div>
              </div>
            </div>

            <div className="wrap">
              <div className="channel panel">
                <div className="inner">
                  <h3>角色负载占比</h3>
                  <div className="data">
                    {P.roleShare.slice(0, 2).map((r) => (
                      <div className="item" key={r.name}>
                        <h4>
                          {r.pct} <small>%</small>
                        </h4>
                        <span>
                          <i className="icon-dot" />
                          {r.name}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="data">
                    {P.roleShare.slice(2).map((r) => (
                      <div className="item" key={r.name}>
                        <h4>
                          {r.pct} <small>%</small>
                        </h4>
                        <span>
                          <i className="icon-dot" />
                          {r.name}
                        </span>
                      </div>
                    ))}
                    <div className="item">
                      <h4>
                        {P.capacity.headroomPct} <small>%</small>
                      </h4>
                      <span>
                        <i className="icon-dot" />
                        容量余量
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="quarter panel">
                <div className="inner">
                  <h3>容量占用率</h3>
                  <div className="chart capacity-panel">
                    <div className="capacity-panel__gauge">
                      <ChartBox options={gaugeOption} />
                      <div className="capacity-panel__rate">
                        {P.capacity.utilizationPct}
                        <small>%</small>
                      </div>
                    </div>
                    <div className="capacity-panel__stats">
                      <div className="item">
                        <h4>{P.kpi.peakQ90Pct}%</h4>
                        <span>
                          <i className="icon-dot" style={{ color: '#6acca3' }} />
                          峰值 Q90
                        </span>
                      </div>
                      <div className="item">
                        <h4>{P.kpi.thresholdPct}%</h4>
                        <span>
                          <i className="icon-dot" style={{ color: '#ed3f35' }} />
                          容量阈值
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="top panel">
              <div className="inner">
                <div className="all">
                  <h3>端口峰值榜</h3>
                  <ul>
                    {P.portRankings.map((p, i) => (
                      <li key={p.name}>
                        <i
                          className={`icon-cup${i + 1}`}
                          style={{
                            color: i === 0 ? '#d93f36' : i === 1 ? '#1890ff' : '#2b6ec8',
                          }}
                        />
                        <span className="top-rank__body">
                          <span className="top-rank__name">{p.name}</span>
                          <span className="top-rank__value">{p.value}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="province">
                  <h3>
                    峰值时段明细 <i className="date">// {activePort?.name} //</i>
                  </h3>
                  <div className="data">
                    <ul className="sup">
                      {P.portRankings.map((p, i) => (
                        <li
                          key={p.name}
                          className={portIdx === i ? 'active' : ''}
                          onMouseEnter={() => setPortIdx(i)}
                        >
                          <span>{p.name}</span>
                          <span>
                            {p.value}{' '}
                            <s className={p.up ? 'icon-up' : 'icon-down'} />
                          </span>
                        </li>
                      ))}
                    </ul>
                    <ul className="sub">
                      {portSubList.map((h) => (
                        <li key={h.label}>
                          <span>{h.label}</span>
                          <span>
                            Q50&nbsp;{h.q50}%{' '}
                            <s className="icon-up" />
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
