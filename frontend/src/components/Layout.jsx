import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import MicroscopeIcon from './MicroscopeIcon'

const navItems = [
  { to: '/', label: '首页', end: true },
  { to: '/detect', label: '图像检测' },
  { to: '/chat', label: '医疗问答' },
  { to: '/history', label: '检测历史' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* 顶栏 */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 group">
            <MicroscopeIcon className="w-9 h-9 shrink-0 text-medical-600 group-hover:text-medical-700 transition" />
            <div className="leading-tight">
              <div className="font-semibold text-medical-700 group-hover:text-medical-500 transition">
                皮肤癌图像检测系统
              </div>
              <div className="text-[11px] text-medical-400">
                Skin Cancer Detection
              </div>
            </div>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            {navItems.map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                end={it.end}
                className={({ isActive }) =>
                  `px-4 py-2 rounded-lg text-sm font-medium transition ${
                    isActive
                      ? 'bg-medical-50 text-medical-700'
                      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`
                }
              >
                {it.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            {user ? (
              <>
                {user.role === 'admin' && (
                  <a
                    href="/admin/"
                    title="管理员入口"
                    className="hidden sm:flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-slate-800 text-white hover:bg-slate-700 transition shadow-sm"
                  >
                    <span>⚙</span> 管理后台
                  </a>
                )}
                <span className="hidden sm:block text-sm text-slate-600">
                  {user.role === 'admin' ? 'admin' : (user.full_name || user.username)}
                </span>
                <button
                  onClick={handleLogout}
                  className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition"
                >
                  退出
                </button>
              </>
            ) : (
              <>
                <Link
                  to="/login"
                  className="text-sm px-3 py-1.5 rounded-lg text-slate-600 hover:bg-slate-50 transition"
                >
                  登录
                </Link>
                <Link
                  to="/register"
                  className="text-sm px-4 py-1.5 rounded-lg bg-medical-600 text-white hover:bg-medical-700 transition shadow-sm"
                >
                  注册
                </Link>
              </>
            )}
          </div>
        </div>

        {/* 移动端导航 */}
        <nav className="md:hidden border-t border-slate-100 flex">
          {navItems.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.end}
              className={({ isActive }) =>
                `flex-1 py-2.5 text-center text-sm font-medium transition ${
                  isActive
                    ? 'text-medical-600 border-b-2 border-medical-500'
                    : 'text-slate-500'
                }`
              }
            >
              {it.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white mt-12">
        <div className="max-w-6xl mx-auto px-4 py-6 text-center space-y-2">
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 inline-block max-w-3xl text-left">
            ⚠️ 医疗免责声明：本系统仅作为皮肤健康自检的辅助工具，AI 检测结果仅供参考，
            不构成医疗诊断，不能替代专业医生的诊断与治疗。如有疑虑请及时就医。
          </p>
          <p className="text-xs text-slate-400">
            皮肤癌图像检测系统 v1.0 · 基于 ResNet50 深度学习模型 · 仅供学习研究使用
          </p>
        </div>
      </footer>
    </div>
  )
}
