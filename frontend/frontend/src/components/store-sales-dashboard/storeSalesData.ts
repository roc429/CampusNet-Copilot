export type MonitorRow = { time: string; address: string; code: string }

export const OVERVIEW_STATS = [
  { value: '2,190', label: '设备总数', color: '#006cff' },
  { value: '190', label: '季度新增', color: '#6acca3' },
  { value: '3,001', label: '运营设备', color: '#6acca3' },
  { value: '108', label: '异常设备', color: '#ed3f35' },
] as const

export const FAULT_ROWS: MonitorRow[] = [
  { time: '20180701', address: '11北京市昌平西路金燕龙写字楼', code: '1000001' },
  { time: '20190601', address: '北京市昌平区城西路金燕龙写字楼', code: '1000002' },
  { time: '20190704', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000003' },
  { time: '20180701', address: '北京市昌平区建路金燕龙写字楼', code: '1000004' },
  { time: '20190701', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000005' },
  { time: '20190701', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000006' },
  { time: '20190701', address: '北京市昌平区建西路金燕龙写字楼', code: '1000007' },
  { time: '20190701', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000008' },
  { time: '20190701', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000009' },
  { time: '20190710', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000010' },
]

export const ABNORMAL_ROWS: MonitorRow[] = [
  { time: '20190701', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000001' },
  { time: '20190701', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000002' },
  { time: '20190703', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000002' },
  { time: '20190704', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000002' },
  { time: '20190705', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000002' },
  { time: '20190706', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000002' },
  { time: '20190707', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000002' },
  { time: '20190708', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000002' },
  { time: '20190709', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000002' },
  { time: '20190710', address: '北京市昌平区建材城西路金燕龙写字楼', code: '1000002' },
]

export const ORDER_PERIODS = ['day365', 'day90', 'day30', 'day1'] as const
export type OrderPeriod = (typeof ORDER_PERIODS)[number]

export const ORDER_DATA: Record<OrderPeriod, { orders: string; amount: string }> = {
  day365: { orders: '20,301,987', amount: '99834' },
  day90: { orders: '301,987', amount: '9834' },
  day30: { orders: '1,987', amount: '3834' },
  day1: { orders: '987', amount: '834' },
}

export const SALES_TYPES = ['year', 'quarter', 'month', 'week'] as const
export type SalesType = (typeof SALES_TYPES)[number]

export const SALES_SERIES: Record<SalesType, [number[], number[]]> = {
  year: [
    [24, 40, 101, 134, 90, 230, 210, 230, 120, 230, 210, 120],
    [40, 64, 191, 324, 290, 330, 310, 213, 180, 200, 180, 79],
  ],
  quarter: [
    [23, 75, 12, 97, 21, 67, 98, 21, 43, 64, 76, 38],
    [43, 31, 65, 23, 78, 21, 82, 64, 43, 60, 19, 34],
  ],
  month: [
    [34, 87, 32, 76, 98, 12, 32, 87, 39, 36, 29, 36],
    [56, 43, 98, 21, 56, 87, 43, 12, 43, 54, 12, 98],
  ],
  week: [
    [43, 73, 62, 54, 91, 54, 84, 43, 86, 43, 54, 53],
    [32, 54, 34, 87, 32, 45, 62, 68, 93, 54, 54, 24],
  ],
}

export const PROVINCE_TOP = [
  { name: '北京', value: '25,179', up: true },
  { name: '河北', value: '23,252', up: false },
  { name: '上海', value: '20,760', up: true },
  { name: '江苏', value: '23,252', up: false },
  { name: '山东', value: '20,760', up: true },
] as const

export const BRAND_SUB = [
  { name: '可爱多', num: '9,086' },
  { name: '娃哈哈', num: '8,341' },
  { name: '喜之郎', num: '7,407' },
  { name: '八喜', num: '6,080' },
  { name: '小洋人', num: '6,724' },
  { name: '好多鱼', num: '2,170' },
] as const

export function shuffleBrandSub() {
  return [...BRAND_SUB].sort(() => 0.5 - Math.random())
}
