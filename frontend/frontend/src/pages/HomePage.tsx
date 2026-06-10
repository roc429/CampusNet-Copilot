import {
  ArrowRight,
  BarChart3,
  Check,
  LineChart,
  Network,
  Wrench,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import brandLogo from '../assets/logo.png'
import heroAnimation from '../assets/1animation.svg'
import iconGraphRag from '../assets/Hybrid GraphRAG.svg'
import iconMcp from '../assets/MCP标准协议.svg'
import iconNemo from '../assets/NeMo安全护栏.svg'
import iconSdn from '../assets/SDN仿真验证.svg'
import iconTimesFm from '../assets/TimesFM预测模型.svg'
import iconSecurity from '../assets/双回路安全验证.svg'
import iconAgents from '../assets/多智能体协同.svg'
import iconTopology from '../assets/智能感知拓扑.svg'
import iconSelfService from '../assets/自助服务交互.svg'
import iconDefense from '../assets/预警式防御.svg'
import iconTroubleshoot from '../assets/故障自动排查.svg'
import iconSecurityAudit from '../assets/安全防护审计.svg'
import iconTrafficAlert from '../assets/流量预警通知.svg'
import iconSelfExperience from '../assets/自动服务体验.svg'
import statAvailability from '../assets/系统可用性.svg'
import statEfficiency from '../assets/运维效率提升.svg'
import statPatrol from '../assets/智能监控守护.svg'
import statAiOps from '../assets/驱动智能运维.svg'
import scenarioVisual from '../assets/应用场景.png'
import dashboardVisual from '../assets/全局可视.png'
import assistantMascot from '../assets/小助手.svg'
import './HomePage.css'

const NAV = [
  { id: 'hero', label: '首页' },
  { id: 'features', label: '产品功能' },
  { id: 'tech', label: '核心技术' },
  { id: 'dashboard', label: '解决方案' },
  { id: 'scenarios', label: '应用场景' },
  { id: 'cta', label: '关于我们' },
] as const

type SectionId = (typeof NAV)[number]['id']

const HERO_CHECKS = [
  '智能体协同联动运维闭环',
  '拓扑知识图谱全域感知',
  '预警式防御主动保障策略',
] as const

const STATS = [
  { value: '99.99%', label: '系统可用性', icon: statAvailability, theme: 'blue' },
  { value: '80%+', label: '运维效率提升', icon: statEfficiency, theme: 'green' },
  { value: '7×24h', label: '智能巡检守护', icon: statPatrol, theme: 'purple' },
  { value: 'AI', label: '驱动智能运维', icon: statAiOps, theme: 'amber' },
] as const

const FEATURES = [
  {
    icon: iconTopology,
    title: '智能拓扑感知',
    desc: '自动发现网络设备与链路关系，实时感知拓扑变化与节点状态。',
  },
  {
    icon: iconDefense,
    title: '预警式防御',
    desc: 'TimesFM 时序预测结合阈值告警，在故障发生前主动预警。',
  },
  {
    icon: iconAgents,
    title: '多智能体协同',
    desc: 'Chat / Retriever / Telemetry / Diagnosis 等 Agent 分工协作。',
  },
  {
    icon: iconSelfService,
    title: '自助服务交互',
    desc: '自然语言提问即可触发诊断，进度可视化与报告一键导出。',
  },
  {
    icon: iconSecurity,
    title: '双向安全验证',
    desc: 'SecurityGuard 语义审计 + SDN dry-run 仿真后再执行修复。',
  },
] as const

const DASHBOARD_ITEMS = [
  { Icon: Network, label: '全域拓扑可视化' },
  { Icon: LineChart, label: '实时流量监控' },
  { Icon: BarChart3, label: '智能告警分析' },
  { Icon: Wrench, label: '运维工单管理' },
] as const

const TECH_STACK = [
  { icon: iconGraphRag, title: 'Hybrid GraphRAG', desc: '混合图检索 + 语义证据链' },
  { icon: iconMcp, title: 'MCP 标准协议', desc: 'Prometheus / NetBox / Grafana 工具总线' },
  { icon: iconTimesFm, title: 'TimesFM 预测引擎', desc: '负载与异常窗口时序预测' },
  { icon: iconNemo, title: 'NeMo 安全护栏', desc: '高风险指令人工审批与审查' },
  { icon: iconSdn, title: 'SDN 仿真验证', desc: 'Mininet 沙箱 dry-run 后再下发' },
] as const

const SCENARIOS = [
  {
    icon: iconTroubleshoot,
    title: '故障自动排查',
    descLines: ['智能诊断根因', '自动修复闭环'],
  },
  {
    icon: iconSecurityAudit,
    title: '安全防护审计',
    descLines: ['恶意变更拦截', '全链路安全审计'],
  },
  {
    icon: iconTrafficAlert,
    title: '流量预警感知',
    descLines: ['高并发预测预警', '态势感知调度'],
  },
  {
    icon: iconSelfExperience,
    title: '自助服务体验',
    descLines: ['一键报障诊断', '知识智能推荐'],
  },
] as const

function HomePage() {
  const navigate = useNavigate()
  const sectionRefs = useRef<Partial<Record<SectionId, HTMLElement>>>({})
  const [activeSection, setActiveSection] = useState<SectionId>('hero')

  const goLogin = useCallback(() => {
    navigate('/login')
  }, [navigate])

  const scrollTo = useCallback((id: SectionId) => {
    sectionRefs.current[id]?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible?.target.id) {
          setActiveSection(visible.target.id as SectionId)
        }
      },
      { threshold: [0.2, 0.4, 0.6] },
    )

    NAV.forEach(({ id }) => {
      const el = sectionRefs.current[id]
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [])

  return (
    <div className="cn-home">
      <header className="cn-home__header">
        <div className="cn-home__container cn-home__header-inner">
          <button type="button" className="cn-home__brand" onClick={() => scrollTo('hero')}>
            <img src={brandLogo} alt="" draggable={false} className="cn-home__brand-logo" />
            <span className="cn-home__brand-name">智网学伴</span>
          </button>

          <nav className="cn-home__nav" aria-label="主导航">
            {NAV.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                className={activeSection === id ? 'is-active' : ''}
                onClick={() => scrollTo(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          <Link to="/login" className="cn-home__header-btn">
            登录 / 注册
          </Link>
        </div>
      </header>

      <main className="cn-home__main">
        {/* Hero */}
        <section
          id="hero"
          ref={(el) => {
            if (el) sectionRefs.current.hero = el
          }}
          className="cn-home__hero"
        >
          <div className="cn-home__hero-bg" aria-hidden="true" />
          <div className="cn-home__container cn-home__hero-grid">
            <div className="cn-home__hero-copy">
              <div className="cn-home__hero-title-row">
                <h1>智网学伴</h1>
                <span className="cn-home__badge">CampusNet Copilot</span>
              </div>
              <p className="cn-home__hero-tagline">拓扑感知 · 预警防御 · 智能运维</p>
              <p className="cn-home__hero-desc">
                基于 Agentic AI 与预置式赋权的拓扑感知型校园网智能运维系统
              </p>
              <ul className="cn-home__hero-checks">
                {HERO_CHECKS.map((item) => (
                  <li key={item}>
                    <Check size={16} strokeWidth={2.5} aria-hidden="true" />
                    {item}
                  </li>
                ))}
              </ul>
              <div className="cn-home__hero-actions">
                <button type="button" className="cn-home__btn cn-home__btn--primary" onClick={goLogin}>
                  立即体验
                </button>
                <button
                  type="button"
                  className="cn-home__btn cn-home__btn--outline"
                  onClick={() => scrollTo('features')}
                >
                  了解更多
                  <ArrowRight size={16} aria-hidden="true" />
                </button>
              </div>
            </div>
            <div className="cn-home__hero-visual">
              <img src={heroAnimation} alt="" draggable={false} className="cn-home__hero-animation" />
            </div>
          </div>

          <div className="cn-home__container">
            <div className="cn-home__stats">
              {STATS.map(({ value, label, icon, theme }) => (
                <div key={label} className={`cn-home__stat cn-home__stat--${theme}`}>
                  <span className="cn-home__stat-icon">
                    <img src={icon} alt="" className="cn-home__stat-icon-img" draggable={false} />
                  </span>
                  <div>
                    <strong>{value}</strong>
                    <span>{label}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Core Features */}
        <section
          id="features"
          ref={(el) => {
            if (el) sectionRefs.current.features = el
          }}
          className="cn-home__section cn-home__section--features"
        >
          <div className="cn-home__container">
            <div className="cn-home__section-head">
              <span className="cn-home__section-label">CORE FEATURES</span>
              <h2>核心能力</h2>
              <p>融合 GraphRAG、MCP 工具总线与 TimesFM 预测，打造校园网智能运维闭环。</p>
            </div>
            <div className="cn-home__feature-grid">
              {FEATURES.map(({ icon, title, desc }) => (
                <article key={title} className="cn-home__feature-card">
                  <span className="cn-home__feature-icon">
                    <img src={icon} alt="" draggable={false} />
                  </span>
                  <h3>{title}</h3>
                  <p>{desc}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* Dashboard Preview */}
        <section
          id="dashboard"
          ref={(el) => {
            if (el) sectionRefs.current.dashboard = el
          }}
          className="cn-home__section cn-home__section--dashboard"
        >
          <div className="cn-home__container cn-home__dashboard-grid">
            <div className="cn-home__dashboard-copy">
              <h2>全局可视 · 一屏掌控</h2>
              <p>
                实时汇聚 Prometheus 指标、NetBox 拓扑与 Agent 诊断结果，运维人员可在统一控制台完成监控、分析与处置。
              </p>
              <ul className="cn-home__dashboard-list">
                {DASHBOARD_ITEMS.map(({ Icon, label }) => (
                  <li key={label}>
                    <span className="cn-home__dashboard-list-icon">
                      <Icon size={28} strokeWidth={1.75} aria-hidden="true" />
                    </span>
                    {label}
                  </li>
                ))}
              </ul>
              <button type="button" className="cn-home__btn cn-home__btn--primary" onClick={goLogin}>
                探索控制台
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
            <div className="cn-home__dashboard-preview" aria-hidden="true">
              <img src={dashboardVisual} alt="" draggable={false} />
            </div>
          </div>
        </section>

        {/* Tech Stack */}
        <section
          id="tech"
          ref={(el) => {
            if (el) sectionRefs.current.tech = el
          }}
          className="cn-home__section cn-home__section--tech"
        >
          <div className="cn-home__container">
            <div className="cn-home__section-head cn-home__section-head--compact">
              <h2>技术驱动 · 创新引领</h2>
            </div>
            <div className="cn-home__tech-grid">
              {TECH_STACK.map(({ icon, title, desc }) => (
                <article key={title} className="cn-home__tech-item">
                  <span className="cn-home__tech-icon">
                    <img src={icon} alt="" draggable={false} />
                  </span>
                  <h3>{title}</h3>
                  <p>{desc}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* Scenarios */}
        <section
          id="scenarios"
          ref={(el) => {
            if (el) sectionRefs.current.scenarios = el
          }}
          className="cn-home__section cn-home__section--scenarios"
        >
          <div className="cn-home__container">
            <div className="cn-home__scenario-layout">
              <div className="cn-home__scenario-head">
                <span className="cn-home__section-label">SCENARIOS</span>
                <h2>应用场景</h2>
                <p>覆盖校园网络运维全场景，满足多角色需求</p>
              </div>

              <div className="cn-home__scenario-cards">
                {SCENARIOS.map(({ icon, title, descLines }) => (
                  <article key={title} className="cn-home__scenario-card">
                    <span className="cn-home__scenario-icon">
                      <img src={icon} alt="" draggable={false} />
                    </span>
                    <h3>{title}</h3>
                    {descLines.map((line) => (
                      <p key={line}>{line}</p>
                    ))}
                  </article>
                ))}
              </div>

              <div className="cn-home__scenario-visual" aria-hidden="true">
                <img src={scenarioVisual} alt="" draggable={false} />
              </div>
            </div>
          </div>
        </section>

        {/* Footer CTA */}
        <section
          id="cta"
          ref={(el) => {
            if (el) sectionRefs.current.cta = el
          }}
          className="cn-home__cta"
        >
          <div className="cn-home__container cn-home__cta-grid">
            <div className="cn-home__cta-copy">
              <h2>智网学伴 让校园网络运维更智能、更高效、更安全</h2>
              <p>立即登录体验 Agentic AI 驱动的校园网智能运维演示系统</p>
              <div className="cn-home__cta-actions">
                <button type="button" className="cn-home__btn cn-home__btn--light" onClick={goLogin}>
                  立即体验系统
                </button>
                <button type="button" className="cn-home__btn cn-home__btn--ghost" onClick={goLogin}>
                  申请演示
                </button>
              </div>
            </div>
            <div className="cn-home__cta-mascot">
              <img src={assistantMascot} alt="" draggable={false} />
            </div>
          </div>
          <footer className="cn-home__footer-note">
            智网学伴 · CampusNet-Copilot · C4-2026
          </footer>
        </section>
      </main>
    </div>
  )
}

export default HomePage
