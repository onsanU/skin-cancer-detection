import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import DetectPage from './pages/DetectPage'
import HistoryPage from './pages/HistoryPage'
import ChatPage from './pages/ChatPage'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import { useAuth } from './contexts/AuthContext'

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        加载中...
      </div>
    )
  }
  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }
  return children
}

export default function App() {
  return (
    <Routes>
      {/* 认证页：全屏独立布局（无顶部导航栏，沉浸感更强） */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* 主站：带顶部导航栏 + 页脚 */}
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/detect" element={<DetectPage />} />
        {/* 医疗问答：需登录（未登录时 ChatPage 内部会跳登录页） */}
        <Route
          path="/chat"
          element={
            <RequireAuth>
              <ChatPage />
            </RequireAuth>
          }
        />
        <Route
          path="/history"
          element={
            <RequireAuth>
              <HistoryPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
