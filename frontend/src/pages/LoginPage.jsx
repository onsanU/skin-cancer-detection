import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import AuthLayout from '../components/AuthLayout'
import PasswordField from '../components/PasswordField'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // 登录成功后的去向：优先回被拦截前的页面（如 /history），
  // 直接从登录页进来的则回主页（而不是直接进检测页）
  const from = location.state?.from || '/'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setErr('')
    setLoading(true)
    try {
      await login(username.trim(), password)
      navigate(from, { replace: true })
    } catch (e) {
      setErr(e.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      eyebrow="01 / 账号登录"
      title={<>精准检测<br />从一张图像开始</>}
      subtitle="登录后可保存每次检测的结果，随时回看历史记录与恶性概率变化趋势，为后续复查提供参考。"
      highlights={[
        { icon: '✓', text: '上传皮肤病变图像，即刻获得良性 / 恶性判断与置信度' },
        { icon: '◎', text: '额外给出 7 类病变类型参考，帮助理解可能的病变方向' },
        { icon: '↺', text: '检测历史云端保存，支持筛选、对比与 CSV 导出' },
      ]}
    >
      <div className="mb-8">
        <div className="auth-eyebrow mb-2">welcome back</div>
        <h2 className="text-2xl font-bold" style={{ color: 'var(--auth-dark)', letterSpacing: '-0.02em' }}>
          登录账号
        </h2>
        <p className="text-sm mt-2" style={{ color: 'var(--auth-muted)' }}>
          还没有账号？
          <Link to="/register" state={{ from }} className="ml-1 font-medium no-underline" style={{ color: 'var(--auth-brand)' }}>
            立即注册 →
          </Link>
        </p>
      </div>

      <form onSubmit={submit} className="space-y-7">
        <div>
          <label className="auth-label mb-3">用户名 / 邮箱</label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
            className="auth-input"
            placeholder="请输入用户名或邮箱"
          />
        </div>

        <PasswordField
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          label="密码"
          placeholder="请输入密码"
          required
          autoComplete="current-password"
        />

        {err && (
          <div
            className="text-sm rounded-lg px-4 py-3"
            style={{
              color: 'var(--auth-error)',
              background: 'rgba(255,79,79,0.06)',
              border: '1.5px solid var(--auth-error-soft)',
            }}
          >
            {err}
          </div>
        )}

        <button type="submit" disabled={loading} className="auth-btn-primary">
          {loading ? '登录中…' : '登 录'}
        </button>
      </form>

      <p className="text-xs mt-6 pt-5" style={{ color: 'var(--auth-muted)', borderTop: '1.5px solid var(--auth-border)' }}>
        💡 提示：检测功能支持游客直接使用，登录仅用于保存历史记录。
      </p>
    </AuthLayout>
  )
}
