import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '../../..')

const csvCandidates = [
  path.join(repoRoot, 'test_data', 'telemetry.csv'),
  path.join(repoRoot, 'telemetry.csv'),
]
const csvPath = csvCandidates.find((p) => fs.existsSync(p))
if (!csvPath) {
  console.error('找不到 telemetry.csv')
  process.exit(1)
}

const topologyPath = path.join(repoRoot, 'NMB', 'campus_topology.json')
const topology = JSON.parse(fs.readFileSync(topologyPath, 'utf8'))

const devicesById = Object.fromEntries(topology.devices.map((d) => [d.device_id, d]))
const zonesById = Object.fromEntries(topology.zones.map((z) => [z.zone_id, z.name]))

/** legacy Mininet CSV dpid → campus_topology.json 设备 */
const CSV_DPID_MAP = {
  5: { deviceId: 'AP-EXAM-301', monitorPort: { switchId: 'SW-TEACH-01', port: 11 } },
  6: { deviceId: 'AP-EXAM-302', monitorPort: { switchId: 'SW-TEACH-01', port: 12 } },
  7: { deviceId: 'AP-EXAM-303', monitorPort: { switchId: 'SW-TEACH-01', port: 13 } },
  8: { deviceId: 'AP-LIB-01', monitorPort: { switchId: 'SW-TEACH-01', port: 14 } },
  9: { deviceId: 'AP-DORM-A1', monitorPort: { switchId: 'SW-DORM-01', port: 11 } },
  10: { deviceId: 'AP-DORM-A2', monitorPort: { switchId: 'SW-DORM-01', port: 12 } },
  13: { deviceId: 'SW-TEACH-01', monitorPort: { switchId: 'SW-TEACH-01', port: 1 } },
  14: { deviceId: 'SW-DORM-01', monitorPort: { switchId: 'SW-DORM-01', port: 1 } },
  15: { deviceId: 'SW-DC-01', monitorPort: { switchId: 'SW-DC-01', port: 1 } },
  16: { deviceId: 'OF-CORE-01', monitorPort: { switchId: 'OF-CORE-01', port: 1 } },
}

const AP_ROLES = new Set(['teaching_ap', 'dorm_ap'])
const ZONE_LABEL = {
  teaching_ap: zonesById['ZONE-TEACH'] ?? '教学楼区域',
  dorm_ap: zonesById['ZONE-DORM'] ?? '宿舍区域',
  agg_switch: zonesById['ZONE-DC'] ?? '数据中心',
  core_switch: zonesById['ZONE-DC'] ?? '数据中心',
}

function resolveRow(row) {
  const mapped = CSV_DPID_MAP[Number(row.dpid)]
  if (!mapped) return null
  const device = devicesById[mapped.deviceId]
  if (!device) return null
  const { switchId, port } = mapped.monitorPort
  return {
    deviceId: mapped.deviceId,
    deviceName: device.name,
    zoneName: zonesById[device.zone_id] ?? device.zone_id,
    portId: `${switchId}-P${port}`,
    switchId,
    port,
    role: row.role,
    zoneLabel: ZONE_LABEL[row.role] ?? device.zone_id,
  }
}

function formatPortId(switchId, port) {
  return `${switchId}-P${port}`
}

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

const roles = [...new Set(rows.map((r) => r.role))].sort()

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

const dcRoles = ['agg_switch', 'core_switch']
const dcLoads = dcRoles.flatMap((role) => {
  const v = roleAvgDuringActive[role]
  return v != null ? [v] : []
})
const partitionLoad = [
  { name: ZONE_LABEL.teaching_ap, value: roleAvgDuringActive.teaching_ap ?? 0 },
  { name: ZONE_LABEL.dorm_ap, value: roleAvgDuringActive.dorm_ap ?? 0 },
  {
    name: ZONE_LABEL.agg_switch,
    value: dcLoads.length
      ? Number((dcLoads.reduce((a, b) => a + b, 0) / dcLoads.length).toFixed(2))
      : 0,
  },
]

const apPorts = peakList
  .filter((r) => AP_ROLES.has(r.role))
  .sort((a, b) => Number(a.dpid) - Number(b.dpid))

const apStatus = apPorts
  .map((r) => {
    const meta = resolveRow(r)
    if (!meta) return null
    const online = Number(r.throughput_bps) > 0 || Number(r.load) > 0.001
    return {
      id: meta.deviceId,
      name: meta.deviceName,
      zone: meta.zoneName,
      uplink: meta.portId,
      loadPct: Number((Number(r.load) * 100).toFixed(2)),
      throughputMbps: Number((Number(r.throughput_bps) / 1e6).toFixed(2)),
      online,
    }
  })
  .filter(Boolean)

const portDetails = peakList
  .map((r) => {
    const meta = resolveRow(r)
    if (!meta) return null
    const up = Number(r.throughput_bps) > 0 || Number(r.load) > 0.001
    return {
      portId: meta.portId,
      deviceId: meta.deviceId,
      deviceName: meta.deviceName,
      port: meta.port,
      zone: meta.zoneName,
      status: up ? 'Up' : 'Down',
      rateMbps: Number((Number(r.throughput_bps) / 1e6).toFixed(2)),
      totalTrafficGb: Number(((Number(r.rx_bytes) + Number(r.tx_bytes)) / 1e9).toFixed(3)),
      dropCount: Number(r.rx_dropped) + Number(r.tx_dropped),
      loadPct: Number((Number(r.load) * 100).toFixed(2)),
      lossPct: Number((Number(r.loss) * 100).toFixed(4)),
    }
  })
  .filter(Boolean)
  .sort((a, b) => b.loadPct - a.loadPct)

const alarms = []
const apAlarmByDevice = new Map()

for (const r of peakList) {
  const meta = resolveRow(r)
  if (!meta) continue
  const load = Number(r.load)
  const loss = Number(r.loss)
  const time = (r.timestamp_iso || `${peakMinute.t.replace(' ', 'T')}:00`)
    .slice(0, 19)
    .replace('T', ' ')

  if (load >= 0.8) {
    alarms.push({
      level: '严重',
      type: '负载超阈',
      time,
      content: `${meta.deviceName}（${meta.deviceId}）负载 ${(load * 100).toFixed(1)}% ≥ 80%`,
    })
  } else if (loss >= 0.01) {
    alarms.push({
      level: '严重',
      type: '丢包异常',
      time,
      content: `${meta.portId} ${meta.deviceName} 丢包率 ${(loss * 100).toFixed(2)}%`,
    })
  } else if (AP_ROLES.has(r.role) && load >= 0.04) {
    const prev = apAlarmByDevice.get(meta.deviceId)
    if (prev && prev._load >= load) continue
    const level = load >= 0.12 ? '警告' : '提示'
    const type = load >= 0.12 ? 'AP高负载' : 'AP负载偏高'
    apAlarmByDevice.set(meta.deviceId, {
      level,
      type,
      time,
      content: `${meta.deviceName}（${meta.deviceId}）负载 ${(load * 100).toFixed(1)}%`,
      _load: load,
    })
  }
}

for (const item of apAlarmByDevice.values()) {
  const { _load: _ignored, ...alarm } = item
  alarms.push(alarm)
}

alarms.sort((a, b) => {
  const rank = { 严重: 0, 警告: 1, 提示: 2 }
  return (rank[a.level] ?? 9) - (rank[b.level] ?? 9)
})

const ruleAlarms = alarms.slice(0, 6)

const loads = peakList.map((r) => Number(r.load))
const apLoads = peakList.filter((r) => AP_ROLES.has(r.role)).map((r) => Number(r.load))
const throughputs = peakList.map((r) => Number(r.throughput_bps))

const out = {
  meta: {
    source: path.basename(csvPath),
    topology: 'NMB/campus_topology.json',
    generatedAt: new Date().toISOString().slice(0, 10),
  },
  kpi: {
    avgLoadPct: Number(((loads.reduce((a, b) => a + b, 0) / loads.length) * 100).toFixed(2)),
    peakApLoadPct: Number((Math.max(...apLoads, 0) * 100).toFixed(2)),
    totalThroughputMbps: Number((throughputs.reduce((a, b) => a + b, 0) / 1e6).toFixed(2)),
    abnormalPortCount: peakList.filter((r) => Number(r.load) >= 0.8 || Number(r.loss) > 0).length,
    portCount: peakList.length,
    updatedAtIso: `${peakMinute.t.replace(' ', 'T')}:00`,
  },
  loadSeries,
  partitionLoad,
  throughputSeries,
  lossHealthSeries,
  apStatus,
  portDetails,
  ruleAlarms,
}

const outPath = path.join(
  repoRoot,
  'frontend/frontend/src/components/monitor-screen/telemetryStaticData.ts',
)
const body = `/** Auto-generated from telemetry.csv + campus_topology.json. Run: node scripts/analyze-telemetry.mjs */\n\nexport const TELEMETRY_STATIC = ${JSON.stringify(out, null, 2)} as const\n\nexport type TelemetryStatic = typeof TELEMETRY_STATIC\n`
fs.writeFileSync(outPath, body, 'utf8')
console.log('written', outPath)
console.log(JSON.stringify({ kpi: out.kpi, apCount: apStatus.length, portCount: portDetails.length }, null, 2))
