import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import loginIllustration from '../assets/login-illustration.png'
import './AuthPage.css'

function RegisterPage() {
  const navigate = useNavigate()
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  async function handleRegisterSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()

    if (!account.trim() || !password.trim()) {
      alert('请输入账号和密码')
      return
    }

    if (!confirmPassword.trim()) {
      alert('请再次输入确认密码')
      return
    }

    if (password !== confirmPassword) {
      alert('两次输入的密码不一致')
      return
    }

    const base = import.meta.env.VITE_API_BASE_URL ?? ''
    try {
      const res = await fetch(`${base}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: account.trim(), password }),
      })
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown; message?: string }
      if (!res.ok) {
        const msg =
          typeof data.detail === 'string'
            ? data.detail
            : Array.isArray(data.detail)
              ? data.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('；')
              : '注册失败'
        alert(msg)
        return
      }
      alert(data.message ?? '注册成功')
      setAccount('')
      setPassword('')
      setConfirmPassword('')
      navigate('/login')
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
          <h2 className="login-title">注册</h2>

          <form className="login-form" onSubmit={handleRegisterSubmit}>
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

            <label className="login-label">
              确认密码
              <div className="login-input">
                <input
                  type="password"
                  placeholder="请再次输入密码"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </div>
            </label>

            <button type="submit" className="login-submit">
              注册
            </button>
          </form>

          <div className="login-bottom">
            已有账号？ <Link className="login-toggle" to="/login">返回登录</Link>
          </div>
        </section>
      </div>
    </div>
  )
}

export default RegisterPage
