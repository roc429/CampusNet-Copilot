import { useCallback, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowLeftRight,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'

import ItemWrap from '../ItemWrap'
import { fetchTelemetryKpi, type TelemetryKpi } from '../monitorScreenApi'
import { TELEMETRY_STATIC } from '../telemetryStaticData'
import { usePolling } from '../usePolling'

const MOCK_KPI: TelemetryKpi = {
  avgLoadPct: TELEMETRY_STATIC.kpi.avgLoadPct,
  peakApLoadPct: TELEMETRY_STATIC.kpi.peakApLoadPct,
  totalThroughputMbps: TELEMETRY_STATIC.kpi.totalThroughputMbps,
  abnormalPortCount: TELEMETRY_STATIC.kpi.abnormalPortCount,
  portCount: TELEMETRY_STATIC.kpi.portCount,
  updatedAt: TELEMETRY_STATIC.kpi.updatedAtIso
    ? new Date(TELEMETRY_STATIC.kpi.updatedAtIso).getTime() / 1000
    : null,
  updatedAtIso: TELEMETRY_STATIC.kpi.updatedAtIso,
}

type CardConfig = {
  title: string
  subtitle: string
  key: keyof Pick<
    TelemetryKpi,
    'avgLoadPct' | 'peakApLoadPct' | 'totalThroughputMbps' | 'abnormalPortCount'
  >
  icon: LucideIcon
  tone: 'blue' | 'orange' | 'red' | 'teal'
  valueColor?: string
  format: (value: number) => { value: string; unit: string }
}

const CARDS: CardConfig[] = [
  {
    title: 'KPI 全网',
    subtitle: '平均负载',
    key: 'avgLoadPct',
    icon: Activity,
    tone: 'orange',
    valueColor: '#FFB800',
    format: (v) => ({ value: v.toFixed(2), unit: '%' }),
  },
  {
    title: 'KPI 峰值',
    subtitle: 'AP+负载%',
    key: 'peakApLoadPct',
    icon: TrendingUp,
    tone: 'blue',
    format: (v) => ({ value: v.toFixed(2), unit: '%' }),
  },
  {
    title: 'KPI 总吞吐',
    subtitle: 'Σ Mbps',
    key: 'totalThroughputMbps',
    icon: ArrowLeftRight,
    tone: 'teal',
    format: (v) => ({ value: v.toFixed(2), unit: 'Mbps' }),
  },
  {
    title: 'KPI 超阈',
    subtitle: '异常端口数',
    key: 'abnormalPortCount',
    icon: AlertTriangle,
    tone: 'red',
    valueColor: '#FF5252',
    format: (v) => ({ value: String(Math.round(v)), unit: '个' }),
  },
]

function StatCard({
  config,
  data,
}: {
  config: CardConfig
  data: TelemetryKpi
}) {
  const Icon = config.icon
  const formatted = config.format(data[config.key])

  return (
    <div className={`ms-stat-card ms-stat-card--${config.tone}`}>
      <div className="ms-stat-card__inner">
        <div className={`ms-stat-card__icon ms-stat-card__icon--${config.tone}`}>
          <Icon strokeWidth={1.75} />
        </div>
        <div className="ms-stat-card__content">
          <div className="ms-stat-card__title">{config.title}</div>
          <div className="ms-stat-card__subtitle">{config.subtitle}</div>
          <div className="ms-stat-card__metric">
            <span
              className="ms-stat-card__value"
              style={config.valueColor ? { color: config.valueColor } : undefined}
            >
              {formatted.value}
            </span>
            <span className="ms-stat-card__unit">{formatted.unit}</span>
          </div>
          {config.key === 'abnormalPortCount' ? (
            <div className="ms-stat-card__hint">load≥80% 等</div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default function CenterKpiCards() {
  const [data, setData] = useState<TelemetryKpi>(MOCK_KPI)

  const load = useCallback(async () => {
    const res = await fetchTelemetryKpi()
    if (res.success) {
      setData(res.data)
    }
  }, [])

  usePolling(load, 5000)

  return (
    <div className="ms-center-kpi">
      <ItemWrap title="核心指标" className="ms-center-kpi__panel" contentClassName="ms-center-kpi__wrap">
        <div className="ms-kpi-grid">
          {CARDS.map((card) => (
            <StatCard key={card.key} config={card} data={data} />
          ))}
        </div>
      </ItemWrap>
    </div>
  )
}
