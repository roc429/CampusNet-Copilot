import { useCallback, useEffect, useRef, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  BookOpen,
  Bot,
  FileBarChart,
  TrendingUp,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import assistantMascot from '../assets/小助手.svg'
import userAvatar from '../assets/用户.svg'
import profileCenterIcon from '../assets/个人中心.svg'
import KnowledgePanel from '../components/KnowledgePanel.tsx'
import MonitoringDashboard from '../components/MonitoringDashboard.tsx'
import StoreSalesDashboard from '../components/store-sales-dashboard/StoreSalesDashboard.tsx'
import './AssistantPage.css'

type Role = 'user' | 'assistant'

type ChatMessage = {
  id: string
  role: Role
  content: string
  at?: number
  suggestions?: string[]
  /** 深度思考模式下由模型流式聚合的推理过程 */
  reasoning?: string
  /** 为 true 时保持「思考过程」展开，便于流式展示 */
  streaming?: boolean
}

type NavKey = 'ai' | 'monitor' | 'capacity' | 'knowledge' | 'report'

const NAV_ITEMS: {
  key: NavKey
  label: string
  Icon: LucideIcon
  accent: 'blue' | 'green' | 'orange' | 'purple' | 'teal'
}[] = [
  { key: 'ai', label: 'AI 助手', Icon: Bot, accent: 'blue' },
  { key: 'monitor', label: '监控指标', Icon: Activity, accent: 'green' },
  { key: 'capacity', label: '预测与容量', Icon: TrendingUp, accent: 'orange' },
  { key: 'knowledge', label: '知识库', Icon: BookOpen, accent: 'purple' },
  { key: 'report', label: '报告中心', Icon: FileBarChart, accent: 'teal' },
]

const WELCOME =
  '你好，我是小智士的 AI 助手。我可以协助你进行校园网络相关问答、使用指引与知识检索。你可以直接在下方的输入框中提出你的问题。'

const initialMessages: ChatMessage[] = [
  {
    id: 'm0',
    role: 'assistant',
    content: WELCOME,
    at: Date.now() - 120_000,
    suggestions: ['网络故障排查', '账号与权限', '监控指标说明', '联系运维'],
  },
]

function formatMsgTime(ts?: number): string {
  if (!ts) {
    return ''
  }
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

type QwenModelId = 'qwen-flash' | 'qwen-plus' | 'qwen-max'

function parseApiDetail(data: unknown): string {
  if (!data || typeof data !== 'object') {
    return '请求失败'
  }
  const d = data as { detail?: unknown }
  if (typeof d.detail === 'string') {
    return d.detail
  }
  if (Array.isArray(d.detail)) {
    const first = d.detail[0] as { msg?: string } | undefined
    if (first && typeof first.msg === 'string') {
      return first.msg
    }
  }
  return '请求失败'
}

function extractStreamDelta(obj: Record<string, unknown>): { r: string; c: string } {
  let rAdd = ''
  let cAdd = ''
  const choices = obj.choices
  if (!Array.isArray(choices) || choices.length === 0) {
    return { r: rAdd, c: cAdd }
  }
  const ch0 = choices[0] as Record<string, unknown>
  const delta = ch0.delta as Record<string, unknown> | undefined
  if (delta && typeof delta === 'object') {
    if (typeof delta.reasoning_content === 'string') {
      rAdd += delta.reasoning_content
    }
    if (typeof delta.content === 'string') {
      cAdd += delta.content
    }
  }
  const msg = ch0.message as Record<string, unknown> | undefined
  if (msg && typeof msg === 'object') {
    if (typeof msg.reasoning_content === 'string') {
      rAdd += msg.reasoning_content
    }
    if (typeof msg.content === 'string') {
      cAdd += msg.content
    }
  }
  return { r: rAdd, c: cAdd }
}

function streamErrorMessage(obj: Record<string, unknown>): string {
  const err = obj.error
  if (err && typeof err === 'object') {
    const msg = (err as { message?: string }).message
    if (typeof msg === 'string' && msg.trim()) {
      return msg.trim()
    }
  }
  return '模型服务返回错误'
}

const PLACEHOLDER_COPY: Record<Exclude<NavKey, 'ai' | 'monitor' | 'knowledge' | 'capacity'>, { title: string; desc: string }> = {
  report: {
    title: '报告中心',
    desc: '这里将生成与导出运维报告、运行月报与专项分析。可后续对接报表模板与定时任务。',
  },
}

function AssistantPage() {
  const navigate = useNavigate()
  const [activeNav, setActiveNav] = useState<NavKey>('ai')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState('s1')
  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({
    s1: initialMessages,
  })
  const messages = messagesBySession[activeSessionId] ?? initialMessages
  const [input, setInput] = useState('')
  const [model, setModel] = useState<QwenModelId>('qwen-flash')
  const [deepThink, setDeepThink] = useState(false)
  const [sending, setSending] = useState(false)
  const listRef = useRef<HTMLDivElement | null>(null)
  const userLabel = localStorage.getItem('user_email')?.split('@')[0] ?? '用户'

  const scrollToBottom = useCallback(() => {
    const el = listRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  function handleLogout() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_email')
    navigate('/login', { replace: true })
  }

  function startNewChat() {
    const id = `s${Date.now()}`
    setActiveSessionId(id)
    setMessagesBySession((prev) => ({ ...prev, [id]: initialMessages }))
    setInput('')
  }

  function clearSessions() {
    setActiveSessionId('s1')
    setMessagesBySession({ s1: initialMessages })
  }

  async function sendMessage() {
    const text = input.trim()
    if (!text || sending) {
      return
    }
    const token = localStorage.getItem('access_token')
    if (!token) {
      alert('请先登录')
      navigate('/login', { replace: true })
      return
    }

    const userId = `u${Date.now()}`
    const pendingId = `p${Date.now()}`
    const sid = activeSessionId
    const historyForApi = [
      ...messages.map((m) => ({ role: m.role, content: m.content })),
      { role: 'user' as const, content: text },
    ]

    setMessagesBySession((prev) => {
      const cur = prev[sid] ?? initialMessages
      return {
        ...prev,
        [sid]: [
          ...cur,
          { id: userId, role: 'user', content: text, at: Date.now() },
          {
            id: pendingId,
            role: 'assistant',
            content: '正在生成回答…',
            at: Date.now(),
            streaming: true,
          },
        ],
      }
    })
    setInput('')
    setSending(true)

    const base = import.meta.env.VITE_API_BASE_URL ?? ''
    const acc = { r: '', c: '' }
    let raf = 0
    const flushStreamUi = () => {
      raf = 0
      setMessagesBySession((prev) => ({
        ...prev,
        [sid]: (prev[sid] ?? []).map((m) =>
          m.id === pendingId
            ? {
                ...m,
                reasoning: acc.r.trim() || undefined,
                content: acc.c.trim() || '正在生成回答…',
                at: Date.now(),
                streaming: true,
              }
            : m,
        ),
      }))
    }
    const scheduleFlush = () => {
      if (raf) {
        return
      }
      raf = requestAnimationFrame(flushStreamUi)
    }

    try {
      const res = await fetch(`${base}/api/chat/completions/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          messages: historyForApi,
          model,
          deep_think: deepThink,
        }),
      })

      if (res.status === 401) {
        await res.text().catch(() => undefined)
        localStorage.removeItem('access_token')
        localStorage.removeItem('user_email')
        setMessagesBySession((prev) => ({
          ...prev,
          [sid]: (prev[sid] ?? []).map((m) =>
            m.id === pendingId
              ? {
                  ...m,
                  content: '登录已过期，请重新登录。',
                  at: Date.now(),
                  reasoning: undefined,
                  streaming: false,
                }
              : m,
          ),
        }))
        navigate('/login', { replace: true })
        return
      }

      if (!res.ok) {
        const raw = await res.text().catch(() => '')
        let msg = '请求失败'
        try {
          msg = parseApiDetail(JSON.parse(raw) as unknown)
        } catch {
          if (raw.trim()) {
            msg = raw.slice(0, 400)
          }
        }
        setMessagesBySession((prev) => ({
          ...prev,
          [sid]: (prev[sid] ?? []).map((m) =>
            m.id === pendingId
              ? {
                  ...m,
                  content: `请求失败：${msg}`,
                  at: Date.now(),
                  reasoning: undefined,
                  streaming: false,
                }
              : m,
          ),
        }))
        return
      }

      if (!res.body) {
        setMessagesBySession((prev) => ({
          ...prev,
          [sid]: (prev[sid] ?? []).map((m) =>
            m.id === pendingId
              ? {
                  ...m,
                  content: '响应异常：无流式正文。',
                  at: Date.now(),
                  reasoning: undefined,
                  streaming: false,
                }
              : m,
          ),
        }))
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let sseError: string | null = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          break
        }
        buffer += decoder.decode(value, { stream: true })
        buffer = buffer.replace(/\r\n/g, '\n')

        let sep: number
        while ((sep = buffer.indexOf('\n\n')) >= 0) {
          const event = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          const lines = event.split('\n').filter((l) => l.trim().length > 0)
          for (const line of lines) {
            if (!line.startsWith('data:')) {
              continue
            }
            const rawJson = line.slice(5).trim()
            if (rawJson === '[DONE]') {
              continue
            }
            let obj: Record<string, unknown>
            try {
              obj = JSON.parse(rawJson) as Record<string, unknown>
            } catch {
              continue
            }
            if (obj.error) {
              sseError = streamErrorMessage(obj)
              break
            }
            const { r, c } = extractStreamDelta(obj)
            acc.r += r
            acc.c += c
            scheduleFlush()
          }
          if (sseError) {
            break
          }
        }
        if (sseError) {
          break
        }
      }

      if (raf) {
        cancelAnimationFrame(raf)
        raf = 0
      }

      if (sseError) {
        setMessagesBySession((prev) => ({
          ...prev,
          [sid]: (prev[sid] ?? []).map((m) =>
            m.id === pendingId
              ? {
                  ...m,
                  content: `请求失败：${sseError}`,
                  at: Date.now(),
                  reasoning: undefined,
                  streaming: false,
                }
              : m,
          ),
        }))
        return
      }

      setMessagesBySession((prev) => ({
        ...prev,
        [sid]: (prev[sid] ?? []).map((m) =>
          m.id === pendingId
            ? {
                ...m,
                reasoning: acc.r.trim() || undefined,
                content: acc.c.trim() || '（模型未返回内容）',
                at: Date.now(),
                streaming: false,
              }
            : m,
        ),
      }))
    } catch {
      if (raf) {
        cancelAnimationFrame(raf)
        raf = 0
      }
      setMessagesBySession((prev) => ({
        ...prev,
        [sid]: (prev[sid] ?? []).map((m) =>
          m.id === pendingId
            ? {
                ...m,
                content: '网络错误：无法连接后端，请确认服务已启动。',
                at: Date.now(),
                reasoning: undefined,
                streaming: false,
              }
            : m,
        ),
      }))
    } finally {
      setSending(false)
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendMessage()
    }
  }

  return (
    <div className={`assistant-app ${sidebarCollapsed ? 'assistant-app--collapsed' : ''}`}>
      <aside className="assistant-sidebar">
        <div className="assistant-sidebar__profile">
          <div className="assistant-sidebar__profile-bg" aria-hidden="true" />
          <div className="assistant-sidebar__avatar-wrap">
            <img
              src={assistantMascot}
              alt=""
              className="assistant-sidebar__avatar"
              draggable={false}
            />
          </div>
          <p className="assistant-sidebar__slogan">智网相伴，畅通校园！</p>
        </div>

        <nav className="assistant-sidebar__nav" aria-label="主导航">
          {NAV_ITEMS.map(({ key, label, Icon, accent }) => (
            <button
              key={key}
              type="button"
              data-accent={accent}
              className={
                activeNav === key
                  ? 'assistant-nav-item assistant-nav-item--active'
                  : 'assistant-nav-item'
              }
              onClick={() => setActiveNav(key)}
            >
              <span className="assistant-nav-item__icon-wrap" aria-hidden="true">
                <Icon className="assistant-nav-item__svg" size={22} strokeWidth={1.85} />
              </span>
              <span className="assistant-nav-item__label">{label}</span>
            </button>
          ))}
        </nav>

        <div className="assistant-sidebar__footer">
          <div className="assistant-user">
            <div className="assistant-user__avatar" aria-hidden="true">
              <img
                src={profileCenterIcon}
                alt=""
                className="assistant-user__avatar-img"
                draggable={false}
              />
            </div>
            <div className="assistant-user__meta">
              <div className="assistant-user__name">{userLabel}</div>
            </div>
            <button
              type="button"
              className="assistant-icon-btn"
              title="退出登录"
              onClick={handleLogout}
            >
              ⎋
            </button>
            <button
              type="button"
              className="assistant-icon-btn"
              title={sidebarCollapsed ? '展开侧栏' : '收起侧栏'}
              onClick={() => setSidebarCollapsed((c) => !c)}
            >
              {sidebarCollapsed ? '⟩' : '⟨'}
            </button>
          </div>
        </div>
      </aside>

      <div
        className={`assistant-main ${activeNav === 'ai' ? 'assistant-main--ai' : ''} ${activeNav === 'monitor' ? 'assistant-main--monitor' : ''} ${activeNav === 'capacity' ? 'assistant-main--capacity' : ''}`}
      >
        {activeNav === 'ai' ? (
          <>
            <header className="assistant-main__header">
              <div className="assistant-main__header-row">
                <h1 className="assistant-main__title">小智士</h1>
                <div className="assistant-main__header-actions">
                  <button type="button" className="assistant-header-btn" onClick={startNewChat}>
                    新对话
                  </button>
                  <button type="button" className="assistant-header-btn assistant-header-btn--ghost" onClick={clearSessions}>
                    清空对话
                  </button>
                </div>
              </div>
              <p className="assistant-main__subtitle">
                面向校园网络的智能运维助手，对话由阿里云百炼通义模型生成；支持知识问答与使用指引。
              </p>
            </header>

            <div className="assistant-chat" ref={listRef}>
              <div className="assistant-messages">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={
                      m.role === 'user'
                        ? 'assistant-msg assistant-msg--user'
                        : 'assistant-msg assistant-msg--assistant'
                    }
                  >
                    <div
                      className={
                        m.role === 'user'
                          ? 'assistant-msg__row assistant-bubble assistant-bubble--user'
                          : 'assistant-msg__row assistant-bubble'
                      }
                    >
                      {m.role === 'assistant' && (
                        <div className="assistant-bubble__avatar" aria-hidden="true">
                          <img
                            src={assistantMascot}
                            alt=""
                            className="assistant-bubble__avatar-img"
                            draggable={false}
                          />
                        </div>
                      )}
                      {m.role === 'user' && (
                        <div
                          className="assistant-bubble__avatar assistant-bubble__avatar--user"
                          aria-hidden="true"
                        >
                          <img
                            src={userAvatar}
                            alt=""
                            className="assistant-bubble__avatar-img"
                            draggable={false}
                          />
                        </div>
                      )}
                      <div className="assistant-bubble__body">
                        {m.role === 'assistant' && m.reasoning?.trim() ? (
                          <details
                            className="assistant-reasoning"
                            {...(m.streaming ? { open: true } : {})}
                          >
                            <summary className="assistant-reasoning__summary">思考过程</summary>
                            <div className="assistant-reasoning__body">{m.reasoning}</div>
                          </details>
                        ) : null}
                        <div className="assistant-bubble__content">{m.content}</div>
                        {m.role === 'assistant' &&
                          m.suggestions &&
                          m.suggestions.length > 0 && (
                            <div className="assistant-bubble__pills">
                              {m.suggestions.map((s) => (
                                <button key={s} type="button" className="assistant-pill">
                                  {s}
                                </button>
                              ))}
                            </div>
                          )}
                      </div>
                    </div>
                    <div className="assistant-msg__meta">
                      {formatMsgTime(m.at)}
                      {m.at ? ' · ' : ''}
                      {m.role === 'assistant' ? 'NETOPS AI' : 'YOU'}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="assistant-input-panel">
              <div className="assistant-input-box">
                <div className="assistant-input-box__toolbar">
                  <label className="assistant-select-wrap assistant-select-wrap--grow">
                    <span className="visually-hidden">模型</span>
                    <select
                      className="assistant-select assistant-select--ghost"
                      value={model}
                      onChange={(e) => setModel(e.target.value as QwenModelId)}
                    >
                      <option value="qwen-flash">通义 · qwen-flash</option>
                      <option value="qwen-plus">通义 · qwen-plus</option>
                      <option value="qwen-max">通义 · qwen-max</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    className={
                      deepThink
                        ? 'assistant-chip-toggle assistant-chip-toggle--on'
                        : 'assistant-chip-toggle'
                    }
                    onClick={() => setDeepThink((d) => !d)}
                  >
                    <span className="assistant-chip-toggle__knob" aria-hidden="true" />
                    深度思考
                  </button>
                </div>
                <div className="assistant-input-box__compose">
                  <textarea
                    className="assistant-input"
                    rows={2}
                    placeholder="请输入您的内容"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={onKeyDown}
                  />
                  <button
                    type="button"
                    className="assistant-send"
                    disabled={sending || !input.trim()}
                    onClick={() => void sendMessage()}
                  >
                    <span aria-hidden="true">➤</span>
                    <span className="visually-hidden">发送</span>
                  </button>
                </div>
              </div>
            </div>
          </>
        ) : activeNav === 'monitor' ? (
          <MonitoringDashboard />
        ) : activeNav === 'capacity' ? (
          <StoreSalesDashboard />
        ) : activeNav === 'knowledge' ? (
          <KnowledgePanel />
        ) : (
          <div className="assistant-placeholder">


            <header className="assistant-placeholder__header">
              <h1 className="assistant-placeholder__title">{PLACEHOLDER_COPY[activeNav].title}</h1>
              <p className="assistant-placeholder__desc">{PLACEHOLDER_COPY[activeNav].desc}</p>
            </header>
            <div className="assistant-placeholder__card" aria-hidden="true">
              <div className="assistant-placeholder__grid" />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default AssistantPage
