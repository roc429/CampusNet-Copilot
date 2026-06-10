import { useState } from 'react'
import type { FormEvent } from 'react'
import { Eye, EyeOff, Lock, Mail } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthPageLayout } from './AuthPageLayout'

function RegisterPage() {
  const navigate = useNavigate()
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

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
    <AuthPageLayout>
      <div className="login-v2__card">
        <div className="login-v2__welcome">欢迎来到小智士</div>
        <h2 className="login-v2__title">注册</h2>

        <form className="login-v2__form" onSubmit={handleRegisterSubmit}>
          <label className="login-v2__label">
            邮箱
            <div className="login-v2__field">
              <span className="login-v2__field-icon">
                <Mail aria-hidden="true" />
              </span>
              <input
                type="email"
                autoComplete="email"
                placeholder="请输入邮箱"
                value={account}
                onChange={(e) => setAccount(e.target.value)}
              />
            </div>
          </label>

          <label className="login-v2__label">
            密码
            <div className="login-v2__field">
              <span className="login-v2__field-icon">
                <Lock aria-hidden="true" />
              </span>
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="请输入密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="login-v2__toggle-pw"
                aria-label={showPassword ? '隐藏密码' : '显示密码'}
                onClick={() => setShowPassword((v) => !v)}
              >
                {showPassword ? <EyeOff /> : <Eye />}
              </button>
            </div>
          </label>

          <label className="login-v2__label">
            确认密码
            <div className="login-v2__field">
              <span className="login-v2__field-icon">
                <Lock aria-hidden="true" />
              </span>
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="请再次输入密码"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              <button
                type="button"
                className="login-v2__toggle-pw"
                aria-label={showConfirmPassword ? '隐藏密码' : '显示密码'}
                onClick={() => setShowConfirmPassword((v) => !v)}
              >
                {showConfirmPassword ? <EyeOff /> : <Eye />}
              </button>
            </div>
          </label>

          <button type="submit" className="login-v2__submit">
            注册
          </button>
        </form>

        <div className="login-v2__footer">
          已有账号？ <Link to="/login">返回登录</Link>
        </div>
      </div>
    </AuthPageLayout>
  )
}

export default RegisterPage
