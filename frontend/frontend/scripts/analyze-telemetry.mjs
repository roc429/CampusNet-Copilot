import fs from 'fs'

const csvPath = new URL('../../../telemetry.csv', import.meta.url)
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

const AP = new Set(['teaching_ap', 'dorm_ap'])
const roles = [...new Set(rows.map((r) => r.role))].sort()
const roleLabels = {
  teaching_ap: '\u6559\u5b66\u533aAP',
  dorm_ap: '\u5bbf\u820d\u533aAP',
  data_access: '\u6570\u636e\u63a5\u5165',
}

const byMinute = {}
for (const r of rows) {
  const t = r.timestamp_iso.slice(0, 16)
  if (!byMinute[t]) byMinute[t] = { rows: [], load: [], tp: [], loss: [] }
  byMinute[t].rows.push(r)
  byMinute[t].load.push(Number(r.load))
  byMinute[t].tp.push(Number(r.throughput_bps))
  byMinute[t].loss.push(Number(r.loss))
}

const activeMinutes = Object.entries(byMinute)
  .filter(([, d]) => d.tp.reduce((a, b) => a + b, 0) > 1e6)
  .sort(([a], [b]) => a.localeCompare(b))

const peakMinute = activeMinutes.reduce(
  (best, [t, d]) => {
    const sum = d.tp.reduce((a, b) => a + b, 0)
    return sum > best.sum ? { t, sum, d } : best
  },
  { t: activeMinutes[0]?.[0] ?? '', sum: 0, d: activeMinutes[0]?.[1] },
)

const pick = (arr, n) => {
  if (arr.length <= n) return arr
  const out = []
  for (let i = 0; i < n; i += 1) {
    out.push(arr[Math.round((i * (arr.length - 1)) / (n - 1))])
  }
  return out
}

const sampledMinutes = pick(activeMinutes.map(([t]) => t), 12)
const loadSeries = sampledMinutes.map((t) => {
  const d = byMinute[t]
  return {
    time: t.slice(11),
    avgLoadPct: Number(((d.load.reduce((a, b) => a + b, 0) / d.load.length) * 100).toFixed(2)),
  }
})
const throughputSeries = sampledMinutes.map((t) => {
  const d = byMinute[t]
  return {
    time: t.slice(11),
    throughputMbps: Number((d.tp.reduce((a, b) => a + b, 0) / 1e6).toFixed(2)),
  }
})
const lossHealthSeries = sampledMinutes.map((t) => {
  const d = byMinute[t]
  const avgLoad = d.load.reduce((a, b) => a + b, 0) / d.load.length
  const avgLoss = (d.loss.reduce((a, b) => a + b, 0) / d.loss.length) * 100
  const healthScore = Math.max(
    0,
    Math.min(100, Number((100 - avgLoad * 100 * 0.5 - avgLoss * 10).toFixed(1))),
  )
  return {
    time: t.slice(11),
    lossPct: Number(avgLoss.toFixed(4)),
    healthScore,
  }
})

const peakRows = peakMinute.d?.rows ?? rows.slice(-12)
const peakLatest = {}
for (const r of peakRows) {
  const key = `${r.dpid}|${r.port}`
  peakLatest[key] = r
}
const peakList = Object.values(peakLatest)

const roleAvgDuringActive = {}
for (const role of roles) {
  const vals = []
  for (const [, d] of activeMinutes) {
    for (const r of d.rows) {
      if (r.role === role) vals.push(Number(r.load))
    }
  }
  roleAvgDuringActive[role] = vals.length
    ? Number(((vals.reduce((a, b) => a + b, 0) / vals.length) * 100).toFixed(2))
    : 0
}

const apPorts = peakList.filter((r) => AP.has(r.role)).sort((a, b) => Number(a.dpid) - Number(b.dpid))
const ap12 = []
for (let i = 0; i < 12; i += 1) {
  const r = apPorts[i]
  if (r) {
    ap12.push({
      id: `AP-${i + 1}`,
      dpid: r.dpid,
      port: Number(r.port),
      role: roleLabels[r.role] || r.role,
      loadPct: Number((Number(r.load) * 100).toFixed(2)),
      throughputMbps: Number((Number(r.throughput_bps) / 1e6).toFixed(2)),
      online: Number(r.throughput_bps) > 0 || Number(r.load) > 0.001,
    })
  } else {
    ap12.push({
      id: `AP-${i + 1}`,
      dpid: '-',
      port: 0,
      role: '\u672a\u63a5\u5165',
      loadPct: 0,
      throughputMbps: 0,
      online: false,
    })
  }
}

const portDetails = peakList
  .sort((a, b) => Number(b.load) - Number(a.load))
  .slice(0, 10)
  .map((r) => ({
    portId: `SW${r.dpid}-P${r.port}`,
    dpid: r.dpid,
    port: Number(r.port),
    role: roleLabels[r.role] || r.role,
    status: Number(r.throughput_bps) > 0 || Number(r.load) > 0.001 ? 'Up' : 'Down',
    rateMbps: Number((Number(r.throughput_bps) / 1e6).toFixed(2)),
    totalTrafficGb: Number(((Number(r.rx_bytes) + Number(r.tx_bytes)) / 1e9).toFixed(3)),
    dropCount: Number(r.rx_dropped) + Number(r.tx_dropped),
    loadPct: Number((Number(r.load) * 100).toFixed(2)),
    lossPct: Number((Number(r.loss) * 100).toFixed(4)),
  }))

const alarms = []
const apAlarmByDpid = new Map()

for (const r of peakList) {
  const load = Number(r.load)
  const loss = Number(r.loss)
  const time = (r.timestamp_iso || peakMinute.t.replace(' ', 'T') + ':00').slice(0, 19).replace('T', ' ')
  if (load >= 0.8) {
    alarms.push({
      level: '\u4e25\u91cd',
      type: '\u8d1f\u8f7d\u8d85\u9608',
      time,
      content: `\u4ea4\u6362\u673a${r.dpid} \u7aef\u53e3${r.port} \u8d1f\u8f7d ${(load * 100).toFixed(1)}% \u2265 80%`,
    })
  } else if (loss > 0) {
    alarms.push({
      level: '\u4e25\u91cd',
      type: '\u4e22\u5305\u5f02\u5e38',
      time,
      content: `\u4ea4\u6362\u673a${r.dpid} \u7aef\u53e3${r.port} \u4e22\u5305\u7387 ${(loss * 100).toFixed(2)}%`,
    })
  } else if (AP.has(r.role) && load >= 0.04) {
    const prev = apAlarmByDpid.get(r.dpid)
    if (prev && prev._load >= load) continue
    const level = load >= 0.12 ? '\u8b66\u544a' : '\u63d0\u793a'
    const type = load >= 0.12 ? 'AP\u9ad8\u8d1f\u8f7d' : 'AP\u8d1f\u8f7d\u504f\u9ad8'
    apAlarmByDpid.set(r.dpid, {
      level,
      type,
      time,
      content: `${roleLabels[r.role]} SW${r.dpid} \u8d1f\u8f7d ${(load * 100).toFixed(1)}%`,
      _load: load,
    })
  }
}

for (const item of apAlarmByDpid.values()) {
  const { _load: _ignored, ...alarm } = item
  alarms.push(alarm)
}

alarms.sort((a, b) => {
  const rank = { '\u4e25\u91cd': 0, '\u8b66\u544a': 1, '\u63d0\u793a': 2 }
  return (rank[a.level] ?? 9) - (rank[b.level] ?? 9)
})

const ruleAlarms = alarms.slice(0, 6)

const loads = peakList.map((r) => Number(r.load))
const apLoads = peakList.filter((r) => AP.has(r.role)).map((r) => Number(r.load))
const throughputs = peakList.map((r) => Number(r.throughput_bps))

const out = {
  kpi: {
    avgLoadPct: Number(((loads.reduce((a, b) => a + b, 0) / loads.length) * 100).toFixed(2)),
    peakApLoadPct: Number((Math.max(...apLoads, 0) * 100).toFixed(2)),
    totalThroughputMbps: Number((throughputs.reduce((a, b) => a + b, 0) / 1e6).toFixed(2)),
    abnormalPortCount: peakList.filter((r) => Number(r.load) >= 0.8 || Number(r.loss) > 0).length,
    portCount: peakList.length,
    updatedAtIso: peakMinute.t.replace(' ', 'T') + ':00',
  },
  loadSeries,
  partitionLoad: roles.map((role) => ({
    name: roleLabels[role] || role,
    value: roleAvgDuringActive[role],
  })),
  throughputSeries,
  lossHealthSeries,
  ap12,
  portDetails,
  ruleAlarms,
}

const outPath = new URL('../src/components/monitor-screen/telemetryStaticData.ts', import.meta.url)
const body = `/** Auto-generated from telemetry.csv analysis. Do not edit manually. */\n\nexport const TELEMETRY_STATIC = ${JSON.stringify(out, null, 2)} as const\n\nexport type TelemetryStatic = typeof TELEMETRY_STATIC\n`
fs.writeFileSync(outPath, body, 'utf8')
console.log('written', outPath.pathname)
console.log(JSON.stringify(out.kpi, null, 2))
