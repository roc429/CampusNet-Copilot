import { useEffect, useState } from 'react'
import { Settings } from 'lucide-react'
import topBg from '../assets/monitor-screen/img/top.png'
import guang from '../assets/monitor-screen/img/guang.png'
import juxing1 from '../assets/monitor-screen/img/headers/juxing1.png'
import ScaleScreen from './monitor-screen/ScaleScreen'
import DeviceOverview from './monitor-screen/panels/DeviceOverview'
import UserOverview from './monitor-screen/panels/UserOverview'
import DeviceAlerts from './monitor-screen/panels/DeviceAlerts'
import CenterKpiCards from './monitor-screen/panels/CenterKpiCards'
import InstallationPlan from './monitor-screen/panels/InstallationPlan'
import AlarmTrend from './monitor-screen/panels/AlarmTrend'
import AlarmRanking from './monitor-screen/panels/AlarmRanking'
import RealtimeAlerts from './monitor-screen/panels/RealtimeAlerts'
import './monitor-screen/MonitoringScreen.css'

const WEEKDAY = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function formatClock(now: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(now.getHours())}: ${pad(now.getMinutes())}: ${pad(now.getSeconds())}`
}

export default function MonitoringDashboard() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const dateYear = now.toISOString().slice(0, 10)
  const dateWeek = WEEKDAY[now.getDay()]
  const dateDay = formatClock(now)

  return (
    <div className="monitor-page">
      <ScaleScreen width={1920} height={1080} fit="fill">
        <div className="ms-root">
          <div className="ms-host-body">
            <header
              className="ms-title-wrap"
              style={{ backgroundImage: `url(${topBg})` }}
            >
              <img
                className="ms-title-wrap__juxing ms-title-wrap__juxing--left"
                src={juxing1}
                alt=""
              />
              <img
                className="ms-title-wrap__juxing ms-title-wrap__juxing--right"
                src={juxing1}
                alt=""
              />
              <div
                className="ms-title-wrap__guang"
                style={{ backgroundImage: `url(${guang})` }}
              />
              <h1 className="ms-title">
                <span className="ms-title__text">互联网设备可视化平台</span>
              </h1>
              <div className="ms-timers">
                {dateYear} {dateWeek} {dateDay}
                <button type="button" className="ms-timers__settings" aria-label="设置">
                  <Settings size={18} strokeWidth={1.75} />
                </button>
              </div>
            </header>

            <div className="ms-contents">
              <div className="ms-col ms-col--left">
                <div className="ms-lr-item">
                  <DeviceOverview />
                </div>
                <div className="ms-lr-item">
                  <UserOverview />
                </div>
                <div className="ms-lr-item ms-lr-item--pad ms-lr-item--bottom">
                  <DeviceAlerts />
                </div>
              </div>

              <div className="ms-col ms-col--center">
                <div className="ms-center-kpi">
                  <AlarmTrend />
                </div>
                <div className="ms-center-bottom">
                  <AlarmRanking />
                </div>
              </div>

              <div className="ms-col ms-col--right">
                <div className="ms-lr-item">
                  <CenterKpiCards />
                </div>
                <div className="ms-lr-item ms-lr-item--pad">
                  <InstallationPlan />
                </div>
                <div className="ms-lr-item ms-lr-item--pad ms-lr-item--bottom">
                  <RealtimeAlerts />
                </div>
              </div>
            </div>
          </div>
        </div>
      </ScaleScreen>
    </div>
  )
}
