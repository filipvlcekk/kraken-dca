import { reactive } from 'vue'

import {
  login as apiLogin,
  logout as apiLogout,
  restoreSession,
  type ApiResponse,
  type SessionResponse,
} from './api'

export type AuthStoreState = {
  authenticated: boolean
  csrfToken: string | null
  restoring: boolean
  loginPending: boolean
  logoutPending: boolean
  error: string | null
}

type AuthStoreApi = {
  restoreSession: () => Promise<ApiResponse<SessionResponse>>
  login: (password: string) => Promise<ApiResponse<SessionResponse>>
  logout: (csrfToken: string) => Promise<ApiResponse<SessionResponse>>
}

export function createAuthStore(api: Partial<AuthStoreApi> = {}) {
  const client: AuthStoreApi = {
    restoreSession: api.restoreSession ?? restoreSession,
    login: api.login ?? apiLogin,
    logout: api.logout ?? apiLogout,
  }
  const state = reactive<AuthStoreState>({
    authenticated: false,
    csrfToken: null,
    restoring: false,
    loginPending: false,
    logoutPending: false,
    error: null,
  })

  async function restore(): Promise<boolean> {
    state.restoring = true
    try {
      const response = await client.restoreSession()
      if (!response.ok) {
        resetSession()
        state.error = response.error.message
        return false
      }
      applySession(response.data)
      state.error = null
      return state.authenticated
    } finally {
      state.restoring = false
    }
  }

  async function login(password: string): Promise<boolean> {
    state.loginPending = true
    state.error = null
    try {
      const response = await client.login(password)
      if (!response.ok) {
        resetSession()
        state.error = response.error.message
        return false
      }
      applySession(response.data)
      if (!state.authenticated) {
        state.error = 'Invalid password.'
        return false
      }
      return true
    } finally {
      state.loginPending = false
    }
  }

  async function logout(): Promise<boolean> {
    if (state.csrfToken === null) {
      resetSession()
      return true
    }

    state.logoutPending = true
    try {
      const response = await client.logout(state.csrfToken)
      resetSession()
      if (!response.ok) {
        state.error = response.error.message
        return false
      }
      state.error = null
      return true
    } finally {
      state.logoutPending = false
    }
  }

  function applySession(session: SessionResponse): void {
    state.authenticated = session.authenticated
    state.csrfToken = session.csrf_token ?? null
    if (!session.authenticated) {
      state.csrfToken = null
    }
  }

  function resetSession(): void {
    state.authenticated = false
    state.csrfToken = null
  }

  return {
    state,
    restore,
    login,
    logout,
  }
}
