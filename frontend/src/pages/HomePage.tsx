import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Check,
  Network,
  RefreshCw,
  ScanSearch,
  Settings2,
  Sparkles,
  Target,
  Waypoints,
} from 'lucide-react'
import { useEffect, useRef } from 'react'
import lottie from 'lottie-web'
import { Link } from 'react-router-dom'
import brandLogo from '../assets/logo.png'
import heroAnimation from '../assets/Man and robot with computers sitting together in workplace.json'
import '../App.css'

const FEATURES = [
  {
    Icon: Network,
    title: '分布式诊断',
    desc: '多智能体协同感知，在校园网络边缘实时捕获异常信号，通过分布式架构减轻核心处理压力，提升诊断颗粒度。',
  },
  {
    Icon: Waypoints,
    title: '推理链路',
    desc: '基于混合图检索增强技术 (Graph-RAG)，建立全路径故障推理模型，精准锁定从接入层到核心层的故障链。',
  },
  {
    Icon: Settings2,
    title: '自适应策略',
    desc: '智能编排运维工具，根据实时流量预测与风险评估，动态生成修复方案，实现策略的毫秒级自适应调整。',
  },
] as const

const FLOW_STEPS = [
  { Icon: Activity, title: '数据采集', en: 'COLLECTION' },
  { Icon: ScanSearch, title: '智能分析', en: 'ANALYSIS' },
  { Icon: Target, title: '根因定位', en: 'LOCATION' },
  { Icon: RefreshCw, title: '处置闭环', en: 'DISPOSAL' },
] as const

const CHECKLIST = [
  '毫秒级全链路时序数据采集',
  '知识增强的大模型深度分析',
  '全自动化剧本编排联动处置',
] as const

function HomePage() {
  const heroAnimationRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!heroAnimationRef.current) {
      return
    }

    const animation = lottie.loadAnimation({
      container: heroAnimationRef.current,
      renderer: 'svg',
      loop: true,
      autoplay: true,
      animationData: heroAnimation,
    })

    return () => {
      animation.destroy()
    }
  }, [])

  return (
    <div className="page">
      <header className="header">
        <div className="container header__inner">
          <div className="header__brand">
            <img src={brandLogo} alt="" className="header__brand-logo" draggable={false} />
            <span className="logo">智网学伴</span>
          </div>
          <nav className="menu">
            <a href="#capabilities">核心能力</a>
            <a href="#workflow">闭环架构</a>
          </nav>
          <div className="header__actions">
            <Link to="/login" className="btn-primary nav-link-button">
              进入系统
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="section hero">
          <div className="container hero__inner">
            <div className="hero__copy">
              <div className="hero__badge">
                <Sparkles className="hero__badge-icon" size={15} strokeWidth={2} aria-hidden />
                智能体驱动的网络运维
              </div>
              <h1 className="hero__title">
                <span className="hero__title-line hero__title-line--dark">面向校园网络的</span>
                <span className="hero__title-line hero__title-line--blue">智能运维助手</span>
              </h1>
              <p className="hero__lead">
                通过多智能体、混合图检索增强、时序预测与工具编排，实现校园网络故障分析、根因追踪、风险预警与联动处置。
              </p>
              <div className="hero__buttons">
                <Link to="/login" className="home-cta-btn home-cta-btn--primary nav-link-button">
                  进入演示
                  <ArrowRight size={18} strokeWidth={2} aria-hidden />
                </Link>
                <button
                  type="button"
                  className="home-cta-btn home-cta-btn--secondary"
                  onClick={() => document.getElementById('capabilities')?.scrollIntoView({ behavior: 'smooth' })}
                >
                  了解更多
                </button>
              </div>
            </div>
            <div className="hero__visual" aria-hidden="true">
              <div ref={heroAnimationRef} className="hero-animation" />
            </div>
          </div>
        </section>

        <section id="capabilities" className="section section-light">
          <div className="container">
            <div className="section-title">
              <h2>核心赋能能力</h2>
              <p>
                融合 AI 大模型与网络观测数据，通过分布式智能体架构，实现从感知到决策的全方位自动化。
              </p>
            </div>
            <div className="feature-grid">
              {FEATURES.map(({ Icon, title, desc }) => (
                <article key={title} className="feature-card feature-card--design">
                  <span className="feature-card__icon-wrap" aria-hidden>
                    <Icon className="feature-card__svg" size={22} strokeWidth={1.75} />
                  </span>
                  <h3>{title}</h3>
                  <p>{desc}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="workflow" className="section section-workflow">
          <div className="container home-workflow">
            <div className="home-workflow__intro">
              <h2 className="home-workflow__title">全流程闭环运维架构</h2>
              <p className="home-workflow__desc">
                从海量数据识别到自动化处置，智网学伴构建了一套严密的逻辑闭环。不仅能发现问题，更懂如何解决问题。
              </p>
              <ul className="home-workflow__list">
                {CHECKLIST.map((text) => (
                  <li key={text} className="home-workflow__list-item">
                    <span className="home-workflow__check" aria-hidden>
                      <Check size={14} strokeWidth={3} />
                    </span>
                    {text}
                  </li>
                ))}
              </ul>
            </div>

            <div className="home-dashboard" aria-hidden>
              <div className="home-dashboard__flow">
                {FLOW_STEPS.map(({ Icon, title, en }, idx) => (
                  <div key={en} className="home-dashboard__flow-track">
                    <div className="home-flow-step">
                      <div className="home-flow-step__icon">
                        <Icon size={20} strokeWidth={1.65} />
                      </div>
                      <div className="home-flow-step__title">{title}</div>
                      <div className="home-flow-step__en">{en}</div>
                    </div>
                    {idx < FLOW_STEPS.length - 1 ? <div className="home-flow-connector" /> : null}
                  </div>
                ))}
              </div>

              <div className="home-dashboard__panels">
                <div className="home-panel home-panel--latency">
                  <div className="home-panel__head">
                    <span className="home-panel__head-title">NETWORK LATENCY</span>
                    <span className="home-panel__live">LIVE</span>
                  </div>
                  <div className="home-latency-bars">
                    {[38, 52, 41, 48, 88].map((h, i) => (
                      <div key={i} className={`home-latency-bar ${i === 4 ? 'home-latency-bar--peak' : ''}`}>
                        <span style={{ height: `${h}%` }} />
                      </div>
                    ))}
                  </div>
                </div>

                <div className="home-panel home-panel--alert">
                  <div className="home-alert__row">
                    <AlertTriangle className="home-alert__icon" size={22} strokeWidth={2} />
                    <span className="home-alert__text">根因检测：核心交换机负载异常</span>
                  </div>
                  <div className="home-confidence">
                    <div className="home-confidence__bar">
                      <span className="home-confidence__fill" />
                    </div>
                    <span className="home-confidence__label">置信度: 98.4%</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default HomePage
