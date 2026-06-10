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
export type ApStatusItem = (typeof TELEMETRY_STATIC.apStatus)[number]
export type PortDetailItem = (typeof TELEMETRY_STATIC.portDetails)[number]
export type RuleAlarmItem = (typeof TELEMETRY_STATIC.ruleAlarms)[number]

/** 规则告警表 — 与 telemetryStaticData.ruleAlarms 同步 */
export const RULE_ALARM_STATIC: RuleAlarmItem[] = [...TELEMETRY_STATIC.ruleAlarms]

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
  return ok([...TELEMETRY_STATIC.apStatus])
}

export async function fetchPortDetails(): Promise<ApiResult<PortDetailItem[]>> {
  return ok([...TELEMETRY_STATIC.portDetails])
}

export async function fetchRuleAlarms(): Promise<ApiResult<RuleAlarmItem[]>> {
  return ok([...RULE_ALARM_STATIC])
}

type TelemetryKpiApiResponse = {
  ok?: boolean
  data?: {
    avgLoadPct?: number
    peakApLoadPct?: number
    totalThroughputMbps?: number
    abnormalPortCount?: number
    portCount?: number
    updatedAt?: number | null
    updatedAtIso?: string | null
  }
  detail?: string
}

/** 核心 KPI — GET :8000/api/monitor/telemetry-kpi */
export async function fetchTelemetryKpi(): Promise<ApiResult<TelemetryKpi>> {
  try {
    const res = await fetch('/api/monitor/telemetry-kpi')
    const body = (await res.json().catch(() => ({}))) as TelemetryKpiApiResponse
    if (!res.ok || !body.ok || !body.data) {
      const msg =
        typeof body.detail === 'string'
          ? body.detail
          : `telemetry-kpi 请求失败 (${res.status})`
      return { success: false, msg }
    }
    const d = body.data
    return {
      success: true,
      data: {
        avgLoadPct: Number(d.avgLoadPct ?? 0),
        peakApLoadPct: Number(d.peakApLoadPct ?? 0),
        totalThroughputMbps: Number(d.totalThroughputMbps ?? 0),
        abnormalPortCount: Number(d.abnormalPortCount ?? 0),
        portCount: Number(d.portCount ?? 0),
        updatedAt:
          d.updatedAt ??
          (d.updatedAtIso ? new Date(d.updatedAtIso).getTime() / 1000 : null),
        updatedAtIso: d.updatedAtIso ?? null,
      },
    }
  } catch (e) {
    return {
      success: false,
      msg: e instanceof Error ? e.message : 'telemetry-kpi 网络错误',
    }
  }
}
