import { Route, Routes } from 'react-router-dom'
import './App.css'
import RequireAuth from './components/RequireAuth.tsx'
import AssistantPage from './pages/AssistantPage.tsx'
import HomePage from './pages/HomePage.tsx'
import LoginPage from './pages/LoginPage.tsx'
import RegisterPage from './pages/RegisterPage.tsx'

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/assistant"
        element={
          <RequireAuth>
            <AssistantPage />
          </RequireAuth>
        }
      />
    </Routes>
  )
}

export default App
