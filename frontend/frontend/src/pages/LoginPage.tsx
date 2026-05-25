import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import loginIllustration from '../assets/login-illustration.png'
import './AuthPage.css'

function LoginPage() {
  const navigate = useNavigate()
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')

  async function handleLoginSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()

    if (!account.trim() || !password.trim()) {
      alert('请输入账号和密码')
      return
    }

    const base = import.meta.env.VITE_API_BASE_URL ?? ''
    try {
      const res = await fetch(`${base}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: account.trim(), password }),
      })
      const data = (await res.json().catch(() => ({}))) as {
        detail?: unknown
        access_token?: string
      }
      if (!res.ok) {
        const msg =
          typeof data.detail === 'string'
            ? data.detail
            : '登录失败'
        alert(msg)
        return
      }
      if (data.access_token) {
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('user_email', account.trim())
      }
      setAccount('')
      setPassword('')
      navigate('/assistant')
    } catch {
      alert('无法连接服务器，请确认后端已启动')
    }
  }

  return (
    <div className="login-page">
      <img src={loginIllustration} alt="" className="login-bg-illus" aria-hidden="true" />
      <span className="corner-triangles corner-triangles--top-left" aria-hidden="true" />
      <span className="corner-triangles corner-triangles--bottom-right" aria-hidden="true" />
      <Link className="login-home-link" to="/">
        首页
      </Link>
      <div className="login-layout">
        <section className="login-left">
          <div className="login-illustration" aria-hidden="true" />
        </section>

        <section className="login-panel">
          <div className="login-brand-small">欢迎来到小智士</div>
          <h2 className="login-title">登录</h2>

          <form className="login-form" onSubmit={handleLoginSubmit}>
            <label className="login-label">
              邮箱
              <div className="login-input">
                <input
                  type="text"
                  placeholder="请输入邮箱"
                  value={account}
                  onChange={(e) => setAccount(e.target.value)}
                />
              </div>
            </label>

            <label className="login-label">
              密码
              <div className="login-input login-input--with-icon">
                <input
                  type="password"
                  placeholder="请输入密码"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <span className="eye" aria-hidden="true">
                  ◌
                </span>
              </div>
            </label>

            <div className="login-form__row">
              <a href="#cta">忘记密码？</a>
            </div>

            <button type="submit" className="login-submit">
              登录
            </button>
          </form>

          <div className="login-bottom">
            还没有账号？ <Link className="login-toggle" to="/register">免费注册</Link>
          </div>
        </section>
      </div>
    </div>
  )
}

export default LoginPage
