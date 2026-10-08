import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import AuthLayout from '../components/AuthLayout'
import PasswordField from '../components/PasswordField'

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // 注册成功后的去向：与登录页保持一致 ——
  // 优先回被拦截前的页面（如 /history），直接从注册页进来的则回主页
  const from = location.state?.from || '/'

  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    confirm: '',
    full_name: '',
  })
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setErr('')
    if (form.password !== form.confirm) {
      setErr('两次输入的密码不一致')
      return
    }
    if (form.password.length < 6) {
      setErr('密码至少 6 个字符')
      return
    }
    if (form.username.trim().length < 3) {
      setErr('用户名至少 3 个字符')
      return
    }
    setLoading(true)
    try {
      await register({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
        full_name: form.full_name.trim(),
      })
      navigate(from, { replace: true })
    } catch (e) {
      setErr(e.message || '注册失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout
      eyebrow="02 / 创建账号"
      title={<>建立你的<br />皮肤健康档案</>}
      subtitle="注册后每次检测都会自动归档，形成个人皮肤病变观察记录，方便长期跟踪同一部位的变化。"
      highlights={[
        { icon: '①', text: '填写基本信息，30 秒即可完成注册' },
        { icon: '②', text: '密码采用 PBKDF2 加密存储，不以明文保存' },
        { icon: '③', text: '个人信息仅用于账号登录与历史记录归属' },
      ]}
    >
      <div className="mb-8">
        <div className="auth-eyebrow mb-2">get started</div>
        <h2 className="text-2xl font-bold" style={{ color: 'var(--auth-dark)', letterSpacing: '-0.02em' }}>
          注册新账号
        </h2>
        <p className="text-sm mt-2" style={{ color: 'var(--auth-muted)' }}>
          已有账号？
          <Link to="/login" state={{ from }} className="ml-1 font-medium no-underline" style={{ color: 'var(--auth-brand)' }}>
            去登录 →
          </Link>
        </p>
      </div>

      <form onSubmit={submit} className="space-y-6">
        <div>
          <label className="auth-label mb-3">用户名 <span style={{ color: 'var(--auth-brand)' }}>*</span></label>
          <input
            value={form.username}
            onChange={set('username')}
            required
            autoComplete="username"
            className="auth-input"
            placeholder="3-32 个字符，用于登录"
          />
        </div>

        <div>
          <label className="auth-label mb-3">邮箱 <span style={{ color: 'var(--auth-brand)' }}>*</span></label>
          <input
            type="email"
            value={form.email}
            onChange={set('email')}
            required
            autoComplete="email"
            className="auth-input"
            placeholder="用于登录与找回账号"
          />
        </div>

        <div>
          <label className="auth-label mb-3">姓名 <span style={{ color: 'var(--auth-muted)' }}>（可选）</span></label>
          <input
            value={form.full_name}
            onChange={set('full_name')}
            autoComplete="name"
            className="auth-input"
            placeholder="将显示在个人信息中"
          />
        </div>

        <div className="grid sm:grid-cols-2 gap-6">
          <PasswordField
            value={form.password}
            onChange={set('password')}
            label="密码"
            placeholder="至少 6 个字符"
            required
            autoComplete="new-password"
          />
          <PasswordField
            value={form.confirm}
            onChange={set('confirm')}
            label="确认密码"
            placeholder="请再次输入"
            required
            autoComplete="new-password"
          />
        </div>

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
          {loading ? '注册中…' : '创建账号'}
        </button>
      </form>

      <p className="text-xs mt-6 pt-5 leading-relaxed" style={{ color: 'var(--auth-muted)', borderTop: '1.5px solid var(--auth-border)' }}>
        点击「创建账号」即表示你已了解：本系统仅作为皮肤健康自检的辅助工具，
        检测结果不构成医疗诊断，不能替代专业医生的诊断与治疗。
      </p>
    </AuthLayout>
  )
}
