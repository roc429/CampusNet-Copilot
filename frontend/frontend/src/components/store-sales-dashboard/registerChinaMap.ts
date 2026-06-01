import * as echarts from 'echarts'

let ready: Promise<void> | null = null

export function ensureChinaMapRegistered(): Promise<void> {
  if (!ready) {
    ready = fetch('/store-sales-dashboard/china-map.json')
      .then((r) => {
        if (!r.ok) throw new Error('china-map.json load failed')
        return r.json()
      })
      .then((geo) => {
        echarts.registerMap('china', geo)
      })
  }
  return ready
}
