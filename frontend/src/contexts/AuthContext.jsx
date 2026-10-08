/**
 * 认证上下文：全局登录状态管理
 */
import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { authApi, tokenStore } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) {
      setUser(null)
      setStats(null)
      setLoading(false)
      return
    }
    try {
      const d = await authApi.me()
      setUser(d.user)
      setStats(d.stats)
    } catch (e) {
      tokenStore.clear()
      setUser(null)
      setStats(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const login = useCallback(async (username, password) => {
    const d = await authApi.login({ username, password })
    tokenStore.set(d.token)
    setUser(d.user)
    return d
  }, [])

  const register = useCallback(async (payload) => {
    const d = await authApi.register(payload)
    tokenStore.set(d.token)
    setUser(d.user)
    return d
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
    setStats(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, stats, loading, login, register, logout, refresh }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return ctx
}
