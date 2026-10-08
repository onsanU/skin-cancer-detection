import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider } from './contexts/AuthContext'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* ⚠️ 根级错误边界：任何子组件渲染异常都不再让整页白屏（连导航都没有）。
        出错时显示可读提示 + 错误信息，页面其它部分继续可用。 */}
    <ErrorBoundary label="root">
      {/* ⚠️ basename 必须与 vite.config.js 的 base 一致（生产环境部署在 /app/ 子路径）
          否则 React Router 收到 /app/login 却匹配 /login → 落进通配符重定向到首页 */}
      <BrowserRouter basename={import.meta.env.BASE_URL}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>
)
