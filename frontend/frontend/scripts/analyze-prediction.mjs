import fs from 'fs'

const csvPath = new URL('../../../prediction.csv', import.meta.url)
const text = fs.readFileSync(csvPath, 'utf8')
const lines = text.trim().split(/\r?\n/)
const headers = lines[0].split(',')
const rows = lines.slice(1).map((line) => {
  const vals = line.split(',')
  const o = {}
  headers.forEach((h, i) => {
    o[h] = vals[i]
  })
  return o
})

const roleLabels = {
  teaching_ap: '教学区AP',
  dorm_ap: '宿舍区AP',
  data_access: '数据接入',
}

const roleColors = {
  teaching_ap: '#1890ff',
  dorm_ap: '#52c41a',
  data_access: '#faad14',
}

const hours = Array.from({ length: 24 }, (_, i) => i + 1)
const thresholdPct = 80

function meanPct(list, key) {
  return list.length
    ? Number(((list.reduce((a, r) => a + +r[key], 0) / list.length) * 100).toFixed(4))
    : 0
}

function avgSeries(filterFn) {
  return hours.map((h) => {
    const pts = rows.filter((r) => filterFn(r) && +r.future_hour === h)
    return {
      hour: h,
      label: `T+${h}h`,
      q10: meanPct(pts, 'q10'),
      q50: meanPct(pts, 'q50'),
      q90: meanPct(pts, 'q90'),
    }
  })
}

function buildMonitorRows(filterFn, codeFn, limit = 12) {
  const seen = new Set()
  const out = []
  const sorted = [...rows].filter(filterFn).sort((a, b) => +b.q90 - +a.q90)
  for (const r of sorted) {
    const key = `${r.dpid}|${r.port}|${r.future_hour}|${r.timestamp_iso}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({
      time: r.timestamp_iso.slice(0, 19).replace('T', ' '),
      address: `SW${r.dpid}-P${r.port} ${roleLabels[r.role] ?? r.role}`,
      code: codeFn(r),
    })
    if (out.length >= limit) break
  }
  return out
}

const allSeries = avgSeries(() => true)
const roleSeries = ['teaching_ap', 'dorm_ap', 'data_access'].map((role) => ({
  role,
  name: roleLabels[role],
  color: roleColors[role],
  series: avgSeries((r) => r.role === role).map(({ hour, q50, q90 }) => ({ hour, q50, q90 })),
}))

const q50all = rows.map((r) => +r.q50 * 100)
const q90all = rows.map((r) => +r.q90 * 100)

const byTs = {}
for (const r of rows) {
  if (!byTs[r.timestamp_iso]) byTs[r.timestamp_iso] = []
  byTs[r.timestamp_iso].push(+r.q50 * 100)
}
const peakTs = Object.entries(byTs).sort(
  (a, b) =>
    b[1].reduce((x, y) => x + y, 0) / b[1].length -
    a[1].reduce((x, y) => x + y, 0) / a[1].length,
)[0][0]

const peakSnapshotSeries = avgSeries((r) => r.timestamp_iso === peakTs)

const portPeaks = ['5|1|teaching_ap', '9|1|dorm_ap', '13|1|data_access'].map((key) => {
  const [dpid, port, role] = key.split('|')
  const pts = rows.filter((r) => r.dpid === dpid && r.port === port && r.role === role)
  const byH = {}
  for (const r of pts) {
    const h = +r.future_hour
    const q50 = +r.q50 * 100
    if (!byH[h] || q50 > byH[h].q50) {
      byH[h] = { q50, q90: +r.q90 * 100, trend: r.trend }
    }
  }
  const peakH = +Object.entries(byH).sort((a, b) => b[1].q50 - a[1].q50)[0][0]
  const h24 = byH[24]
  const hourTop = Object.entries(byH)
    .sort((a, b) => b[1].q50 - a[1].q50)
    .slice(0, 5)
    .map(([h, v]) => ({
      label: `T+${h}h`,
      q50: Number(v.q50.toFixed(2)),
      q90: Number(v.q90.toFixed(2)),
    }))
  return {
    portId: `SW${dpid}-P${port}`,
    role: roleLabels[role],
    peakHour: peakH,
    peakQ50: Number(byH[peakH].q50.toFixed(2)),
    peakQ90: Number(byH[peakH].q90.toFixed(2)),
    h24Q50: Number(h24.q50.toFixed(2)),
    h24Q90: Number(h24.q90.toFixed(2)),
    trend: byH[peakH].trend,
    hourTop,
  }
})

const avgLoad = q50all.reduce((a, b) => a + b, 0) / q50all.length
const peakQ50 = Math.max(...q50all)
const peakQ90 = Math.max(...q90all)

const overviewStats = [
  { value: String(Object.keys(byTs).length), label: '预测快照数', color: '#006cff' },
  { value: '3', label: '监控端口数', color: '#6acca3' },
  { value: `${avgLoad.toFixed(1)}%`, label: '平均预测负载', color: '#6acca3' },
  { value: String(rows.filter((r) => r.risk === 'True').length), label: '风险预测点', color: '#ed3f35' },
]

const riskMonitorRows = buildMonitorRows(
  (r) => r.risk === 'True',
  (r) => `风险 Q90 ${(+r.q90 * 100).toFixed(2)}% T+${r.future_hour}h`,
)

const exceedCiRows = buildMonitorRows(
  (r) => r.exceed_confidence_interval === 'True',
  (r) => `超历史CI T+${r.future_hour}h Q50 ${(+r.q50 * 100).toFixed(2)}%`,
)

const roleAvgLoad = ['teaching_ap', 'dorm_ap', 'data_access'].map((role) => {
  const pts = rows.filter((r) => r.role === role)
  return { name: roleLabels[role], value: meanPct(pts, 'q50') }
})

const hourlyBar = [1, 3, 6, 9, 12, 15, 18, 21, 24].map((h) => {
  const p = allSeries.find((x) => x.hour === h)
  return { label: `T+${h}h`, q50: p?.q50 ?? 0, q90: p?.q90 ?? 0 }
})

const HORIZON_KEYS = ['all', 'peak', 'front', 'back']
const horizonFilters = {
  all: { label: '146次快照', filter: () => true },
  peak: { label: '峰值窗口', filter: (r) => r.timestamp_iso === peakTs },
  front: { label: 'T+1~12h', filter: (r) => +r.future_hour <= 12 },
  back: { label: 'T+13~24h', filter: (r) => +r.future_hour > 12 },
}

const horizonStats = {}
const horizonSeries = {}
for (const key of HORIZON_KEYS) {
  const { filter } = horizonFilters[key]
  const subset = rows.filter(filter)
  horizonStats[key] = {
    avgQ50: Number(meanPct(subset, 'q50').toFixed(2)),
    maxQ90: Number((Math.max(...subset.map((r) => +r.q90 * 100), 0)).toFixed(2)),
    pointCount: subset.length,
  }
  if (key === 'front') {
    horizonSeries[key] = avgSeries(filter).filter((p) => p.hour <= 12)
  } else if (key === 'back') {
    horizonSeries[key] = avgSeries(filter).filter((p) => p.hour > 12)
  } else {
    horizonSeries[key] = avgSeries(filter)
  }
}

const roleShareTotal = roleAvgLoad.reduce((a, b) => a + b.value, 0)
const roleShare = roleAvgLoad.map((r) => ({
  name: r.name,
  pct: roleShareTotal ? Number(((r.value / roleShareTotal) * 100).toFixed(0)) : 0,
  avgLoad: Number(r.value.toFixed(2)),
}))

const capacityUtilPct = Number(((peakQ90 / thresholdPct) * 100).toFixed(1))
const capacityHeadroomPct = Number((100 - capacityUtilPct).toFixed(1))

const portRankings = [...portPeaks]
  .sort((a, b) => b.peakQ50 - a.peakQ50)
  .map((p, i) => ({
    name: p.portId,
    role: p.role,
    value: `${p.peakQ50}%`,
    up: p.trend !== 'falling',
    rank: i + 1,
    hourTop: p.hourTop,
  }))

const out = {
  meta: {
    source: 'prediction.csv',
    model: 'TimesFM 2.5-200M',
    metric: 'load',
    horizonHours: 24,
    rowCount: rows.length,
    snapshotCount: Object.keys(byTs).length,
    peakSnapshotAt: peakTs,
    analyzedAt: '2026-05-29',
  },
  kpi: {
    avgLoadPct: Number(avgLoad.toFixed(2)),
    peakQ50Pct: Number(peakQ50.toFixed(2)),
    peakQ90Pct: Number(peakQ90.toFixed(2)),
    thresholdPct,
    portCount: 3,
    riskPointCount: rows.filter((r) => r.risk === 'True').length,
    exceedThresholdCount: rows.filter((r) => r.exceed_threshold === 'True').length,
    exceedCiCount: rows.filter((r) => r.exceed_confidence_interval === 'True').length,
  },
  capacity: {
    baseCapacityPct: Number(avgLoad.toFixed(2)),
    peakBufferPct: Number(peakQ90.toFixed(2)),
    thresholdPct,
    utilizationPct: capacityUtilPct,
    headroomPct: capacityHeadroomPct,
    recommendation:
      peakQ90 < thresholdPct
        ? '预测峰值负载（Q90）远低于 80% 阈值，可维持现有容量；建议在 T+1h~T+6h 窗口保持常规监控。'
        : '预测峰值接近或超过 80% 阈值，建议在峰值窗口前扩容或启用动态调度。',
  },
  overviewStats,
  riskMonitorRows,
  exceedCiRows,
  rolePie: roleAvgLoad.map((r) => ({ name: r.name, value: Number(r.value.toFixed(2)) })),
  hourlyBar,
  horizonKeys: HORIZON_KEYS,
  horizonLabels: Object.fromEntries(HORIZON_KEYS.map((k) => [k, horizonFilters[k].label])),
  horizonStats,
  horizonSeries,
  roleShare,
  allSeries,
  peakSnapshotSeries,
  roleSeries,
  portPeaks,
  portRankings,
}

const outPath = new URL('../src/components/store-sales-dashboard/predictionStaticData.ts', import.meta.url)
const body = `/** Auto-generated from prediction.csv — TimesFM 负载预测静态分析 */\n\nexport const PREDICTION_STATIC = ${JSON.stringify(out, null, 2)} as const\n\nexport type PredictionStatic = typeof PREDICTION_STATIC\nexport type HorizonKey = typeof PREDICTION_STATIC.horizonKeys[number]\n`
fs.writeFileSync(outPath, body, 'utf8')
console.log('written', outPath.pathname)
