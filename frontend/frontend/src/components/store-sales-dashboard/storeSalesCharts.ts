import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import type { SalesType } from './storeSalesData'
import { SALES_SERIES } from './storeSalesData'
import geoCoordMap from './geoCoordMap.json'

type FlowPair = [[{ name: string }], [{ name: string; value: number }]]

const BJData: FlowPair[] = [
  [[{ name: '新乡' }], [{ name: '新乡', value: 200 }]],
  [[{ name: '新乡' }], [{ name: '呼和浩特', value: 90 }]],
  [[{ name: '新乡' }], [{ name: '哈尔滨', value: 90 }]],
  [[{ name: '新乡' }], [{ name: '石家庄', value: 90 }]],
  [[{ name: '新乡' }], [{ name: '昆明', value: 30 }]],
  [[{ name: '新乡' }], [{ name: '北京', value: 100 }]],
  [[{ name: '新乡' }], [{ name: '长春', value: 40 }]],
  [[{ name: '新乡' }], [{ name: '重庆', value: 40 }]],
  [[{ name: '新乡' }], [{ name: '贵阳', value: 50 }]],
  [[{ name: '新乡' }], [{ name: '南宁', value: 30 }]],
  [[{ name: '新乡' }], [{ name: '济南', value: 10 }]],
  [[{ name: '新乡' }], [{ name: '太原', value: 40 }]],
  [[{ name: '新乡' }], [{ name: '西安', value: 60 }]],
  [[{ name: '新乡' }], [{ name: '武汉', value: 50 }]],
  [[{ name: '新乡' }], [{ name: '合肥', value: 40 }]],
  [[{ name: '新乡' }], [{ name: '南京', value: 30 }]],
  [[{ name: '新乡' }], [{ name: '沈阳', value: 20 }]],
  [[{ name: '新乡' }], [{ name: '成都', value: 10 }]],
]

const SHData: FlowPair[] = [
  [[{ name: '九江' }], [{ name: '九江', value: 200 }]],
  [[{ name: '九江' }], [{ name: '长沙', value: 95 }]],
  [[{ name: '九江' }], [{ name: '武汉', value: 30 }]],
  [[{ name: '九江' }], [{ name: '南昌', value: 20 }]],
  [[{ name: '九江' }], [{ name: '合肥', value: 70 }]],
  [[{ name: '九江' }], [{ name: '南京', value: 60 }]],
  [[{ name: '九江' }], [{ name: '福州', value: 50 }]],
  [[{ name: '九江' }], [{ name: '上海', value: 100 }]],
  [[{ name: '九江' }], [{ name: '深圳', value: 100 }]],
]

const GZData: FlowPair[] = [
  [[{ name: '新疆玛纳斯基地' }], [{ name: '新疆玛纳斯基地', value: 200 }]],
  [[{ name: '新疆玛纳斯基地' }], [{ name: '  ', value: 90 }]],
  [[{ name: '新疆玛纳斯基地' }], [{ name: ' ', value: 40 }]],
  [[{ name: '新疆玛纳斯基地' }], [{ name: '呼和浩特', value: 90 }]],
  [[{ name: '新疆玛纳斯基地' }], [{ name: '昆明', value: 40 }]],
  [[{ name: '新疆玛纳斯基地' }], [{ name: '成都', value: 10 }]],
  [[{ name: '新疆玛纳斯基地' }], [{ name: '兰州', value: 95 }]],
  [[{ name: '新疆玛纳斯基地' }], [{ name: '银川', value: 90 }]],
  [[{ name: '新疆玛纳斯基地' }], [{ name: '西宁', value: 80 }]],
]

const planePath =
  'path://M.6,1318.313v-89.254l-319.9-221.799l0.073-208.063c0.521-84.662-26.629-121.796-63.961-121.491c-37.332-0.305-64.482,36.829-63.961,121.491l0.073,208.063l-319.9,221.799v89.254l330.343-157.288l12.238,241.308l-134.449,92.931l0.531,42.034l175.125-42.917l175.125,42.917l0.531-42.034l-134.449-92.931l12.238-241.308L1705'

const geo = geoCoordMap as unknown as Record<string, [number, number]>

function convertData(data: FlowPair[]) {
  const res: { coord: [number, number] }[][] = []
  for (const item of data) {
    const from = geo[item[0][0].name]
    const to = geo[item[1][0].name]
    if (from && to) {
      res.push([{ coord: from }, { coord: to }])
    }
  }
  return res
}

const mapColors = ['#3ed4ff', '#ffa022', '#a6c84c']

export function buildChinaMapOption(): EChartsOption {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const series: any[] = []
  ;[
    ['新乡', BJData],
    ['九江', SHData],
    ['新疆', GZData],
  ].forEach((item, i) => {
    const label = item[0] as string
    const data = item[1] as FlowPair[]
    const color = mapColors[i]
    series.push(
      {
        name: `${label} Top10`,
        type: 'lines',
        zlevel: 1,
        effect: {
          show: true,
          period: 6,
          trailLength: 0.7,
          color: '#fff',
          symbolSize: 3,
        },
        lineStyle: { color, width: 0, curveness: 0.2 },
        data: convertData(data),
      },
      {
        name: `${label} Top10`,
        type: 'lines',
        zlevel: 2,
        effect: {
          show: true,
          period: 6,
          trailLength: 0,
          symbol: planePath,
          symbolSize: 15,
        },
        lineStyle: { color, width: 1, opacity: 0.4, curveness: 0.2 },
        data: convertData(data),
      },
      {
        name: `${label} Top10`,
        type: 'effectScatter',
        coordinateSystem: 'geo',
        zlevel: 2,
        rippleEffect: { brushType: 'stroke' },
        label: { show: true, position: 'right', formatter: '{b}' },
        symbolSize: (val: number[]) => val[2] / 8,
        itemStyle: { color },
        data: data.map((row) => ({
          name: row[1][0].name,
          value: [...geo[row[1][0].name], row[1][0].value],
        })),
      },
    )
  })

  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: {
      orient: 'vertical',
      top: 'bottom',
      left: 'right',
      data: ['北京 Top10', '上海 Top10', '广州 Top10'],
      textStyle: { color: '#2b6ec8' },
      selectedMode: 'single',
    },
    geo: {
      map: 'china',
      zoom: 1.2,
      roam: true,
      itemStyle: {
        areaColor: '#c8e3f8',
        borderColor: '#6eb5ff',
      },
      emphasis: {
        itemStyle: { areaColor: '#a8d4f5' },
        label: { show: false },
      },
    },
    series,
  } as EChartsOption
}

export const pieOption: EChartsOption = {
  tooltip: {
    trigger: 'item',
    formatter: '{a} <br/>{b} : {c} ({d}%)',
  },
  series: [
    {
      name: '地区',
      type: 'pie',
      radius: ['10%', '70%'],
      center: ['50%', '50%'],
      roseType: 'radius',
      data: [
        { value: 20, name: '云南' },
        { value: 5, name: '北京' },
        { value: 15, name: '山东' },
        { value: 25, name: '河北' },
        { value: 20, name: '江苏' },
        { value: 35, name: '浙江' },
        { value: 30, name: '四川' },
        { value: 40, name: '湖北' },
      ],
      label: { fontSize: 10, color: '#2b6ec8' },
      labelLine: { length: 8, length2: 10 },
    },
  ],
  color: ['#006cff', '#60cda0', '#ed8884', '#ff9f7f', '#0096ff', '#9fe6b8', '#32c5e9', '#1d9dff'],
}

const barPlaceholder = {
  name: '',
  value: 1200,
  itemStyle: { color: '#c5dff5' },
  emphasis: { itemStyle: { color: '#c5dff5' } },
  tooltip: { extraCssText: 'opacity:0' },
}

export const usersBarOption: EChartsOption = {
  tooltip: {
    trigger: 'item',
    axisPointer: { type: 'shadow' },
  },
  grid: {
    left: '0',
    right: '3%',
    bottom: '3%',
    top: '5%',
    containLabel: true,
    show: true,
    borderColor: 'rgba(43, 110, 200, 0.25)',
  },
  xAxis: [
    {
      type: 'category',
      data: ['上海', '广州', '北京', '深圳', '合肥', '', '......', '', '杭州', '厦门', '济南', '成都', '重庆'],
      axisTick: { alignWithLabel: false, show: false },
      axisLabel: { color: '#2b6ec8' },
    },
  ],
  yAxis: [
    {
      type: 'value',
      axisTick: { show: false },
      axisLabel: { color: '#2b6ec8' },
      splitLine: { lineStyle: { color: 'rgba(43, 110, 200, 0.15)' } },
    },
  ],
  series: [
    {
      name: '用户统计',
      type: 'bar',
      barWidth: '60%',
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#5eb3ff' },
          { offset: 1, color: '#2b6ec8' },
        ]),
      },
      data: [2100, 1900, 1700, 1560, 1400, barPlaceholder, barPlaceholder, barPlaceholder, 900, 750, 600, 480, 240],
    },
  ],
}

export function buildSalesLineOption(type: SalesType): EChartsOption {
  const [expected, actual] = SALES_SERIES[type]
  return {
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
      axisTick: { show: false },
      axisLabel: { color: '#2b6ec8' },
      axisLine: { show: false },
      boundaryGap: false,
    },
    yAxis: {
      type: 'value',
      axisTick: { show: false },
      axisLabel: { color: '#2b6ec8' },
      axisLine: { show: false },
    },
    legend: {
      textStyle: { color: '#2b6ec8' },
      right: '10%',
    },
    grid: {
      show: true,
      top: '20%',
      left: '3%',
      right: '4%',
      bottom: '3%',
      borderColor: 'rgba(43, 110, 200, 0.25)',
      containLabel: true,
    },
    series: [
      {
        name: '预期销售额',
        type: 'line',
        smooth: true,
        data: expected,
        itemStyle: { color: '#1890ff' },
      },
      {
        name: '实际销售额',
        type: 'line',
        smooth: true,
        data: actual,
        itemStyle: { color: '#ed3f35' },
      },
    ],
  }
}

export const gaugeOption = {
  series: [
    {
      type: 'pie',
      radius: ['130%', '150%'],
      center: ['50%', '80%'],
      label: { show: false },
      startAngle: 180,
      data: [
        {
          value: 100,
          itemStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: '#5eb3ff' },
                { offset: 1, color: '#2b6ec8' },
              ],
            },
          },
        },
        { value: 100, itemStyle: { color: '#c5dff5' } },
        { value: 200, itemStyle: { color: 'transparent' } },
      ],
    },
  ],
} as EChartsOption
