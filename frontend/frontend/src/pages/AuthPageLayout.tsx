import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import './LoginPage.css'

type AuthPageLayoutProps = {
  children: ReactNode
}

export function AuthPageLayout({ children }: AuthPageLayoutProps) {
  return (
    <div className="login-v2">
      <div className="login-v2__bg" aria-hidden="true" />

      <header className="login-v2__header">
        <Link className="login-v2__home" to="/">
          首页
        </Link>
      </header>

      <main className="login-v2__main">
        <section className="login-v2__promo">
          <div className="login-v2__copy">
            <h1 className="login-v2__art-title">
              <span className="login-v2__art-line">
                <span className="login-v2__art-word">智能连接</span>
                <span className="login-v2__art-accent">未来</span>
              </span>
              <span className="login-v2__art-line login-v2__art-line--sub">数据驱动价值</span>
            </h1>
          </div>
        </section>

        <section className="login-v2__aside">{children}</section>
      </main>
    </div>
  )
}
