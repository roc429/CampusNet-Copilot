import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

type Props = { children: ReactNode }

function RequireAuth({ children }: Props) {
  const location = useLocation()
  const token = localStorage.getItem('access_token')
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}

export default RequireAuth
