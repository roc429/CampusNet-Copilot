/** Auto-generated from telemetry.csv + campus_topology.json. Run: node scripts/analyze-telemetry.mjs */

export const TELEMETRY_STATIC = {
  "meta": {
    "source": "telemetry.csv",
    "topology": "NMB/campus_topology.json",
    "generatedAt": "2026-06-10"
  },
  "kpi": {
    "avgLoadPct": 29.15,
    "peakApLoadPct": 73.47,
    "totalThroughputMbps": 4396.37,
    "abnormalPortCount": 10,
    "portCount": 10,
    "updatedAtIso": "2026-06-01T09:59:00"
  },
  "loadSeries": [
    {
      "time": "08:00",
      "avgLoadPct": 20.81
    },
    {
      "time": "08:14",
      "avgLoadPct": 20.31
    },
    {
      "time": "08:27",
      "avgLoadPct": 20.67
    },
    {
      "time": "08:41",
      "avgLoadPct": 21.11
    },
    {
      "time": "08:55",
      "avgLoadPct": 21.5
    },
    {
      "time": "09:08",
      "avgLoadPct": 22.47
    },
    {
      "time": "09:22",
      "avgLoadPct": 22.71
    },
    {
      "time": "09:35",
      "avgLoadPct": 24.3
    },
    {
      "time": "09:49",
      "avgLoadPct": 26.94
    },
    {
      "time": "10:03",
      "avgLoadPct": 27.12
    },
    {
      "time": "10:16",
      "avgLoadPct": 28.78
    },
    {
      "time": "10:30",
      "avgLoadPct": 29.54
    }
  ],
  "partitionLoad": [
    {
      "name": "教学楼区域",
      "value": 25.84
    },
    {
      "name": "宿舍区域",
      "value": 8.5
    },
    {
      "name": "数据中心",
      "value": 29.35
    }
  ],
  "throughputSeries": [
    {
      "time": "08:00",
      "throughputMbps": 14202.61
    },
    {
      "time": "08:14",
      "throughputMbps": 14279.11
    },
    {
      "time": "08:27",
      "throughputMbps": 14660.67
    },
    {
      "time": "08:41",
      "throughputMbps": 15982.48
    },
    {
      "time": "08:55",
      "throughputMbps": 15238.59
    },
    {
      "time": "09:08",
      "throughputMbps": 14717.37
    },
    {
      "time": "09:22",
      "throughputMbps": 15863.25
    },
    {
      "time": "09:35",
      "throughputMbps": 15740.72
    },
    {
      "time": "09:49",
      "throughputMbps": 15777.54
    },
    {
      "time": "10:03",
      "throughputMbps": 15317.89
    },
    {
      "time": "10:16",
      "throughputMbps": 17068.19
    },
    {
      "time": "10:30",
      "throughputMbps": 4179.72
    }
  ],
  "lossHealthSeries": [
    {
      "time": "08:00",
      "lossPct": 0.228,
      "healthScore": 87.3
    },
    {
      "time": "08:14",
      "lossPct": 0.205,
      "healthScore": 87.8
    },
    {
      "time": "08:27",
      "lossPct": 0.2567,
      "healthScore": 87.1
    },
    {
      "time": "08:41",
      "lossPct": 0.1823,
      "healthScore": 87.6
    },
    {
      "time": "08:55",
      "lossPct": 0.24,
      "healthScore": 86.8
    },
    {
      "time": "09:08",
      "lossPct": 0.2505,
      "healthScore": 86.3
    },
    {
      "time": "09:22",
      "lossPct": 0.269,
      "healthScore": 86
    },
    {
      "time": "09:35",
      "lossPct": 0.5563,
      "healthScore": 82.3
    },
    {
      "time": "09:49",
      "lossPct": 0.787,
      "healthScore": 78.7
    },
    {
      "time": "10:03",
      "lossPct": 0.9688,
      "healthScore": 76.8
    },
    {
      "time": "10:16",
      "lossPct": 1.2275,
      "healthScore": 73.3
    },
    {
      "time": "10:30",
      "lossPct": 1.426,
      "healthScore": 71
    }
  ],
  "apStatus": [
    {
      "id": "AP-EXAM-301",
      "name": "301考场无线AP",
      "zone": "教学楼区域",
      "uplink": "SW-TEACH-01-P11",
      "loadPct": 27.78,
      "throughputMbps": 27.78,
      "online": true
    },
    {
      "id": "AP-EXAM-302",
      "name": "302考场无线AP",
      "zone": "教学楼区域",
      "uplink": "SW-TEACH-01-P12",
      "loadPct": 73.47,
      "throughputMbps": 66.76,
      "online": true
    },
    {
      "id": "AP-EXAM-303",
      "name": "303考场无线AP",
      "zone": "教学楼区域",
      "uplink": "SW-TEACH-01-P13",
      "loadPct": 19.51,
      "throughputMbps": 19.51,
      "online": true
    },
    {
      "id": "AP-LIB-01",
      "name": "图书馆无线AP",
      "zone": "教学楼区域",
      "uplink": "SW-TEACH-01-P14",
      "loadPct": 14.24,
      "throughputMbps": 14.24,
      "online": true
    },
    {
      "id": "AP-DORM-A1",
      "name": "宿舍A1无线AP",
      "zone": "宿舍区域",
      "uplink": "SW-DORM-01-P11",
      "loadPct": 16.14,
      "throughputMbps": 16.14,
      "online": true
    },
    {
      "id": "AP-DORM-A2",
      "name": "宿舍A2无线AP",
      "zone": "宿舍区域",
      "uplink": "SW-DORM-01-P12",
      "loadPct": 11.39,
      "throughputMbps": 11.39,
      "online": true
    }
  ],
  "portDetails": [
    {
      "portId": "SW-TEACH-01-P12",
      "deviceId": "AP-EXAM-302",
      "deviceName": "302考场无线AP",
      "port": 12,
      "zone": "教学楼区域",
      "status": "Up",
      "rateMbps": 66.76,
      "totalTrafficGb": 0.563,
      "dropCount": 11828,
      "loadPct": 73.47,
      "lossPct": 7.09
    },
    {
      "portId": "SW-TEACH-01-P1",
      "deviceId": "SW-TEACH-01",
      "deviceName": "教学楼汇聚交换机",
      "port": 1,
      "zone": "教学楼区域",
      "status": "Up",
      "rateMbps": 413.62,
      "totalTrafficGb": 1.057,
      "dropCount": 3220,
      "loadPct": 41.36,
      "lossPct": 0.31
    },
    {
      "portId": "SW-DC-01-P1",
      "deviceId": "SW-DC-01",
      "deviceName": "数据中心汇聚交换机",
      "port": 1,
      "zone": "数据中心",
      "status": "Up",
      "rateMbps": 370.29,
      "totalTrafficGb": 1.464,
      "dropCount": 3518,
      "loadPct": 37.03,
      "lossPct": 0.38
    },
    {
      "portId": "OF-CORE-01-P1",
      "deviceId": "OF-CORE-01",
      "deviceName": "核心OpenFlow交换机",
      "port": 1,
      "zone": "数据中心",
      "status": "Up",
      "rateMbps": 3278.73,
      "totalTrafficGb": 1.087,
      "dropCount": 32436,
      "loadPct": 32.79,
      "lossPct": 0.4
    },
    {
      "portId": "SW-TEACH-01-P11",
      "deviceId": "AP-EXAM-301",
      "deviceName": "301考场无线AP",
      "port": 11,
      "zone": "教学楼区域",
      "status": "Up",
      "rateMbps": 27.78,
      "totalTrafficGb": 1.508,
      "dropCount": 286,
      "loadPct": 27.78,
      "lossPct": 0.41
    },
    {
      "portId": "SW-TEACH-01-P13",
      "deviceId": "AP-EXAM-303",
      "deviceName": "303考场无线AP",
      "port": 13,
      "zone": "教学楼区域",
      "status": "Up",
      "rateMbps": 19.51,
      "totalTrafficGb": 0.217,
      "dropCount": 292,
      "loadPct": 19.51,
      "lossPct": 0.6
    },
    {
      "portId": "SW-DORM-01-P1",
      "deviceId": "SW-DORM-01",
      "deviceName": "宿舍汇聚交换机",
      "port": 1,
      "zone": "宿舍区域",
      "status": "Up",
      "rateMbps": 177.92,
      "totalTrafficGb": 1.583,
      "dropCount": 242,
      "loadPct": 17.79,
      "lossPct": 0.05
    },
    {
      "portId": "SW-DORM-01-P11",
      "deviceId": "AP-DORM-A1",
      "deviceName": "宿舍A1无线AP",
      "port": 11,
      "zone": "宿舍区域",
      "status": "Up",
      "rateMbps": 16.14,
      "totalTrafficGb": 1.209,
      "dropCount": 36,
      "loadPct": 16.14,
      "lossPct": 0.09
    },
    {
      "portId": "SW-TEACH-01-P14",
      "deviceId": "AP-LIB-01",
      "deviceName": "图书馆无线AP",
      "port": 14,
      "zone": "教学楼区域",
      "status": "Up",
      "rateMbps": 14.24,
      "totalTrafficGb": 0.98,
      "dropCount": 90,
      "loadPct": 14.24,
      "lossPct": 0.26
    },
    {
      "portId": "SW-DORM-01-P12",
      "deviceId": "AP-DORM-A2",
      "deviceName": "宿舍A2无线AP",
      "port": 12,
      "zone": "宿舍区域",
      "status": "Up",
      "rateMbps": 11.39,
      "totalTrafficGb": 0.783,
      "dropCount": 16,
      "loadPct": 11.39,
      "lossPct": 0.06
    }
  ],
  "ruleAlarms": [
    {
      "level": "严重",
      "type": "丢包异常",
      "time": "2026-06-01 09:59:45",
      "content": "SW-TEACH-01-P12 302考场无线AP 丢包率 7.09%"
    },
    {
      "level": "警告",
      "type": "AP高负载",
      "time": "2026-06-01 09:59:45",
      "content": "301考场无线AP（AP-EXAM-301）负载 27.8%"
    },
    {
      "level": "警告",
      "type": "AP高负载",
      "time": "2026-06-01 09:59:45",
      "content": "303考场无线AP（AP-EXAM-303）负载 19.5%"
    },
    {
      "level": "警告",
      "type": "AP高负载",
      "time": "2026-06-01 09:59:45",
      "content": "图书馆无线AP（AP-LIB-01）负载 14.2%"
    },
    {
      "level": "警告",
      "type": "AP高负载",
      "time": "2026-06-01 09:59:45",
      "content": "宿舍A1无线AP（AP-DORM-A1）负载 16.1%"
    },
    {
      "level": "提示",
      "type": "AP负载偏高",
      "time": "2026-06-01 09:59:45",
      "content": "宿舍A2无线AP（AP-DORM-A2）负载 11.4%"
    }
  ]
} as const

export type TelemetryStatic = typeof TELEMETRY_STATIC
