/**
 * 监控大屏数据层 — 静态数据来自 telemetry.csv 分析结果，后期可替换为真实 API
 */

import { TELEMETRY_STATIC } from './telemetryStaticData'

const delay = () => new Promise<void>((r) => setTimeout(r, 200))

export type ApiResult<T> = { success: true; data: T } | { success: false; msg: string }

async function ok<T>(data: T): Promise<ApiResult<T>> {
  await delay()
  return { success: true, data }
}

export type LoadSeriesPoint = { time: string; avgLoadPct: number }
export type ThroughputSeriesPoint = { time: string; throughputMbps: number }
export type LossHealthPoint = { time: string; lossPct: number; healthScore: number }
export type PartitionLoadItem = { name: string; value: number }
export type ApStatusItem = (typeof TELEMETRY_STATIC.ap12)[number]
export type PortDetailItem = (typeof TELEMETRY_STATIC.portDetails)[number]
export type RuleAlarmItem = (typeof TELEMETRY_STATIC.ruleAlarms)[number]

/** 规则告警表 — 6 条静态演示数据（无缝滚动） */
export const RULE_ALARM_STATIC: RuleAlarmItem[] = [
  {
    level: '警告',
    type: 'AP高负载',
    time: '2026-05-29 16:56:55',
    content: '教学区AP SW5 负载 16.6%',
  },
  {
    level: '警告',
    type: 'AP高负载',
    time: '2026-05-29 16:56:55',
    content: '教学区AP SW8 负载 13.5%',
  },
  {
    level: '提示',
    type: 'AP负载偏高',
    time: '2026-05-29 16:56:55',
    content: '宿舍区AP SW9 负载 9.6%',
  },
  {
    level: '提示',
    type: 'AP负载偏高',
    time: '2026-05-29 16:56:55',
    content: '教学区AP SW7 负载 6.8%',
  },
  {
    level: '提示',
    type: 'AP负载偏高',
    time: '2026-05-29 16:56:55',
    content: '宿舍区AP SW10 负载 5.7%',
  },
  {
    level: '提示',
    type: 'AP负载偏高',
    time: '2026-05-29 16:56:55',
    content: '教学区AP SW6 负载 4.9%',
  },
]

export type TelemetryKpi = {
  avgLoadPct: number
  peakApLoadPct: number
  totalThroughputMbps: number
  abnormalPortCount: number
  portCount: number
  updatedAt: number | null
  updatedAtIso: string | null
}

export async function fetchPortLoadSeries(): Promise<ApiResult<LoadSeriesPoint[]>> {
  return ok([...TELEMETRY_STATIC.loadSeries])
}

export async function fetchPartitionLoad(): Promise<ApiResult<PartitionLoadItem[]>> {
  return ok([...TELEMETRY_STATIC.partitionLoad])
}

export async function fetchThroughputSeries(): Promise<ApiResult<ThroughputSeriesPoint[]>> {
  return ok([...TELEMETRY_STATIC.throughputSeries])
}

export async function fetchLossHealthSeries(): Promise<ApiResult<LossHealthPoint[]>> {
  return ok([...TELEMETRY_STATIC.lossHealthSeries])
}

export async function fetchApStatusList(): Promise<ApiResult<ApStatusItem[]>> {
  return ok([...TELEMETRY_STATIC.ap12])
}

export async function fetchPortDetails(): Promise<ApiResult<PortDetailItem[]>> {
  return ok([...TELEMETRY_STATIC.portDetails])
}

export async function fetchRuleAlarms(): Promise<ApiResult<RuleAlarmItem[]>> {
  return ok([...RULE_ALARM_STATIC])
}

export async function fetchTelemetryKpi(): Promise<ApiResult<TelemetryKpi>> {
  const k = TELEMETRY_STATIC.kpi
  return ok({
    avgLoadPct: k.avgLoadPct,
    peakApLoadPct: k.peakApLoadPct,
    totalThroughputMbps: k.totalThroughputMbps,
    abnormalPortCount: k.abnormalPortCount,
    portCount: k.portCount,
    updatedAt: k.updatedAtIso ? new Date(k.updatedAtIso).getTime() / 1000 : null,
    updatedAtIso: k.updatedAtIso,
  })
}
