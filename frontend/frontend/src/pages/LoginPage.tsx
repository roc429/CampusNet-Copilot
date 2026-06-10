import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Eye, EyeOff, Lock, Mail } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthPageLayout } from './AuthPageLayout'

const REMEMBER_KEY = 'login_remember_email'

function LoginPage() {
  const navigate = useNavigate()
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem(REMEMBER_KEY)
    if (saved) {
      setAccount(saved)
      setRememberMe(true)
    }
  }, [])

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
      if (rememberMe) {
        localStorage.setItem(REMEMBER_KEY, account.trim())
      } else {
        localStorage.removeItem(REMEMBER_KEY)
      }
      setPassword('')
      navigate('/assistant')
    } catch {
      alert('无法连接服务器，请确认后端已启动')
    }
  }

  return (
    <AuthPageLayout>
      <div className="login-v2__card">
        <div className="login-v2__welcome">欢迎来到小智士</div>
        <h2 className="login-v2__title">登录</h2>

        <form className="login-v2__form" onSubmit={handleLoginSubmit}>
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
                autoComplete="current-password"
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

          <div className="login-v2__options">
            <label className="login-v2__remember">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
              />
              记住我
            </label>
            <a className="login-v2__forgot" href="#forgot">
              忘记密码？
            </a>
          </div>

          <button type="submit" className="login-v2__submit">
            登录
          </button>
        </form>

        <div className="login-v2__footer">
          还没有账号？ <Link to="/register">免费注册</Link>
        </div>
      </div>
    </AuthPageLayout>
  )
}

export default LoginPage
