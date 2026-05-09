import { Clock, Filter, Laptop, MoreVertical, Network, RefreshCw } from 'lucide-react'

const ALARMS = [
  {
    level: 'CRITICAL' as const,
    device: 'SW-CORE-01',
    content: '链路中断 - Port 12 GigaEth',
    duration: '12m 45s',
    time: '14:23:05',
  },
  {
    level: 'WARNING' as const,
    device: 'AP-FLOOR2-04',
    content: 'CPU负载过高 (>85%)',
    duration: '5m 12s',
    time: '14:15:22',
  },
  {
    level: 'INFO' as const,
    device: 'UPS-SERVER-ROOM',
    content: '电池自检已启动',
    duration: '1m 05s',
    time: '14:10:00',
  },
  {
    level: 'CRITICAL' as const,
    device: 'RT-EDGE-BGP',
    content: 'BGP 邻居关系中断',
    duration: '34m 12s',
    time: '13:58:12',
  },
]

function MiniAreaChart({ variant }: { variant: 'cpu' | 'mem' }) {
  const fill =
    variant === 'cpu'
      ? 'url(#monitorCpuGrad)'
      : 'url(#monitorMemGrad)'
  return (
    <svg className="monitor-mini-chart" viewBox="0 0 200 64" preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="monitorCpuGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(33, 150, 243, 0.42)" />
          <stop offset="100%" stopColor="rgba(33, 150, 243, 0.05)" />
        </linearGradient>
        <linearGradient id="monitorMemGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(100, 181, 246, 0.38)" />
          <stop offset="100%" stopColor="rgba(100, 181, 246, 0.06)" />
        </linearGradient>
      </defs>
      <path
        fill={fill}
        d={
          variant === 'cpu'
            ? 'M0,48 L20,42 L40,50 L60,28 L80,38 L100,22 L120,35 L140,18 L160,30 L180,12 L200,20 L200,64 L0,64 Z'
            : 'M0,52 L25,48 L50,40 L75,44 L100,32 L125,38 L150,28 L175,35 L200,30 L200,64 L0,64 Z'
        }
      />
      <path
        fill="none"
        stroke={variant === 'cpu' ? '#1976d2' : '#42a5f5'}
        strokeWidth="1.5"
        d={
          variant === 'cpu'
            ? 'M0,48 L20,42 L40,50 L60,28 L80,38 L100,22 L120,35 L140,18 L160,30 L180,12 L200,20'
            : 'M0,52 L25,48 L50,40 L75,44 L100,32 L125,38 L150,28 L175,35 L200,30'
        }
      />
    </svg>
  )
}

function DonutLoss() {
  return (
    <div className="monitor-donut-wrap">
      <svg className="monitor-donut" viewBox="0 0 100 100" aria-hidden>
        <circle cx="50" cy="50" r="38" fill="none" stroke="#e3f2fd" strokeWidth="10" />
        <circle
          cx="50"
          cy="50"
          r="38"
          fill="none"
          stroke="#26a69a"
          strokeWidth="10"
          strokeDasharray="232 6"
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
        />
      </svg>
      <div className="monitor-donut__center">
        <span className="monitor-donut__pct">0.02%</span>
        <span className="monitor-donut__ok">HEALTHY</span>
      </div>
    </div>
  )
}

function LatencyChart() {
  return (
    <svg className="monitor-line-chart" viewBox="0 0 400 120" preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="monitorLatFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(33, 150, 243, 0.22)" />
          <stop offset="100%" stopColor="rgba(33, 150, 243, 0)" />
        </linearGradient>
      </defs>
      <path
        fill="url(#monitorLatFill)"
        d="M0,90 L40,88 L80,72 L120,78 L160,55 L200,62 L240,48 L280,52 L320,38 L360,42 L400,35 L400,120 L0,120 Z"
      />
      <path
        fill="none"
        stroke="#1976d2"
        strokeWidth="2.5"
        d="M0,90 L40,88 L80,72 L120,78 L160,55 L200,62 L240,48 L280,52 L320,38 L360,42 L400,35"
      />
      <text x="368" y="32" className="monitor-line-chart__tag">
        8ms
      </text>
    </svg>
  )
}

function ThroughputChart() {
  return (
    <svg className="monitor-throughput-chart" viewBox="0 0 400 120" preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="monitorUpGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(33, 150, 243, 0.32)" />
          <stop offset="100%" stopColor="rgba(33, 150, 243, 0)" />
        </linearGradient>
        <linearGradient id="monitorDnGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(255, 152, 0, 0.28)" />
          <stop offset="100%" stopColor="rgba(255, 152, 0, 0)" />
        </linearGradient>
      </defs>
      <path
        fill="url(#monitorDnGrad)"
        d="M0,95 L50,88 L100,92 L150,80 L200,85 L250,72 L300,78 L350,65 L400,70 L400,120 L0,120 Z"
      />
      <path
        fill="url(#monitorUpGrad)"
        d="M0,100 L50,95 L100,98 L150,88 L200,92 L250,82 L300,86 L350,75 L400,78 L400,120 L0,120 Z"
      />
      <path
        fill="none"
        stroke="#ff8f00"
        strokeWidth="2"
        d="M0,95 L50,88 L100,92 L150,80 L200,85 L250,72 L300,78 L350,65 L400,70"
      />
      <path
        fill="none"
        stroke="#1565c0"
        strokeWidth="2"
        d="M0,100 L50,95 L100,98 L150,88 L200,92 L250,82 L300,86 L350,75 L400,78"
      />
      <text x="12" y="28" className="monitor-throughput-chart__overlay">
        1.2 Gbps
      </text>
    </svg>
  )
}

function levelClass(level: (typeof ALARMS)[number]['level']) {
  if (level === 'CRITICAL') return 'monitor-alarm-badge--critical'
  if (level === 'WARNING') return 'monitor-alarm-badge--warning'
  return 'monitor-alarm-badge--info'
}

export default function MonitoringDashboard() {
  return (
    <div className="monitor-page">
      <header className="monitor-page__head">
        <div className="monitor-page__head-row">
          <div className="monitor-page__head-text">
            <h1 className="monitor-page__title">网络与设备运行监控面板</h1>
            <p className="monitor-page__subtitle">实时基础设施性能监控</p>
          </div>
          <div className="monitor-page__toolbar">
            <button type="button" className="monitor-chip">
              <Clock size={16} strokeWidth={1.75} aria-hidden />
              最近 6 小时
            </button>
            <button type="button" className="monitor-chip">
              <RefreshCw size={16} strokeWidth={1.75} aria-hidden />
              5秒 刷新
            </button>
            <button type="button" className="monitor-chip">
              <Filter size={16} strokeWidth={1.75} aria-hidden />
              过滤条件
            </button>
          </div>
        </div>
      </header>

      <div className="monitor-page__body">
        <div className="monitor-row monitor-row--3">
          <article className="monitor-card">
            <div className="monitor-card__top">
              <span className="monitor-card__label">CPU 使用率</span>
              <button type="button" className="monitor-card__menu" aria-label="更多">
                <MoreVertical size={18} strokeWidth={1.5} />
              </button>
            </div>
            <div className="monitor-card__metric">
              <span className="monitor-card__value">42%</span>
              <span className="monitor-card__unit">当前值</span>
            </div>
            <MiniAreaChart variant="cpu" />
          </article>

          <article className="monitor-card">
            <div className="monitor-card__top">
              <span className="monitor-card__label">内存使用率</span>
              <button type="button" className="monitor-card__menu" aria-label="更多">
                <MoreVertical size={18} strokeWidth={1.5} />
              </button>
            </div>
            <div className="monitor-card__metric">
              <span className="monitor-card__value">65%</span>
              <span className="monitor-card__unit">当前值</span>
            </div>
            <MiniAreaChart variant="mem" />
          </article>

          <article className="monitor-card monitor-card--donut">
            <div className="monitor-card__top">
              <span className="monitor-card__label">丢包率</span>
              <button type="button" className="monitor-card__menu" aria-label="更多">
                <MoreVertical size={18} strokeWidth={1.5} />
              </button>
            </div>
            <DonutLoss />
          </article>
        </div>

        <div className="monitor-row monitor-row--2">
          <article className="monitor-card monitor-card--wide">
            <div className="monitor-card__top monitor-card__top--spread">
              <span className="monitor-card__label">网络时延 (ms)</span>
              <div className="monitor-stat-pills">
                <span className="monitor-stat-pill">Max: 12ms</span>
                <span className="monitor-stat-pill">Min: 4ms</span>
              </div>
            </div>
            <div className="monitor-chart-box">
              <LatencyChart />
            </div>
          </article>

          <article className="monitor-card monitor-card--wide">
            <div className="monitor-card__top monitor-card__top--spread">
              <span className="monitor-card__label">网络吞吐量 (bits/sec)</span>
              <div className="monitor-legend">
                <span>
                  <i className="monitor-legend__dot monitor-legend__dot--up" /> 上行
                </span>
                <span>
                  <i className="monitor-legend__dot monitor-legend__dot--dn" /> 下行
                </span>
              </div>
            </div>
            <div className="monitor-chart-box">
              <ThroughputChart />
            </div>
          </article>
        </div>

        <div className="monitor-row monitor-row--2">
          <article className="monitor-card monitor-card--ap">
            <div className="monitor-card__top monitor-card__top--spread">
              <span className="monitor-card__label">AP 在线数量</span>
              <button type="button" className="monitor-link-btn">
                查看详情
              </button>
            </div>
            <div className="monitor-ap-stats">
              <span>
                <strong className="monitor-ap-stats__on">128</strong> 在线{' '}
                <span className="monitor-ap-stats__pct">(94%)</span>
              </span>
              <span>
                <strong className="monitor-ap-stats__off">8</strong> 离线{' '}
                <span className="monitor-ap-stats__pct-off">(6%)</span>
              </span>
            </div>
            <div className="monitor-ap-bar" role="presentation">
              <span className="monitor-ap-bar__on" style={{ width: '94%' }} />
              <span className="monitor-ap-bar__off" style={{ width: '6%' }} />
            </div>
          </article>

          <article className="monitor-card monitor-card--table">
            <div className="monitor-card__top monitor-card__top--spread">
              <span className="monitor-card__label">最近告警列表</span>
              <button type="button" className="monitor-outline-btn">
                所有告警
              </button>
            </div>
            <div className="monitor-table-wrap">
              <table className="monitor-table">
                <thead>
                  <tr>
                    <th>级别</th>
                    <th>设备名称</th>
                    <th>告警内容</th>
                    <th>持续时间</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {ALARMS.map((row) => (
                    <tr key={`${row.device}-${row.time}`}>
                      <td>
                        <span className={`monitor-alarm-badge ${levelClass(row.level)}`}>{row.level}</span>
                      </td>
                      <td>{row.device}</td>
                      <td>{row.content}</td>
                      <td>{row.duration}</td>
                      <td className="monitor-table__time">{row.time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </div>

        <div className="monitor-row monitor-row--summary">
          <article className="monitor-summary-card">
            <div className="monitor-summary-card__icon" aria-hidden>
              <Network size={22} strokeWidth={1.65} />
            </div>
            <div className="monitor-summary-card__text">
              <div className="monitor-summary-card__label">活动子网</div>
              <div className="monitor-summary-card__value">24个</div>
            </div>
          </article>
          <article className="monitor-summary-card">
            <div className="monitor-summary-card__icon" aria-hidden>
              <Laptop size={22} strokeWidth={1.65} />
            </div>
            <div className="monitor-summary-card__text">
              <div className="monitor-summary-card__label">在线客户端</div>
              <div className="monitor-summary-card__value">1,245个</div>
            </div>
          </article>
          <article className="monitor-hero-card">
            <div className="monitor-hero-card__content">
              <h2 className="monitor-hero-card__title">系统运行状态良好</h2>
              <p className="monitor-hero-card__desc">
                当前所有核心链路时延低于 10ms，SLA 达标率 99.98%。
              </p>
            </div>
            <button type="button" className="monitor-hero-card__fab" aria-label="添加">
              +
            </button>
          </article>
        </div>
      </div>
    </div>
  )
}
