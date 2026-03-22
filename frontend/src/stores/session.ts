import { defineStore } from 'pinia'

import { apiRequest, clearStoredToken, setStoredToken } from '../lib/api'
import type { UserProfile } from '../types'

interface LoginResponse {
  token: string
  user: UserProfile
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    token: '',
    currentUser: null as UserProfile | null,
    isReady: false,
    isAuthenticating: false,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.token && state.currentUser),
    displayName: (state) =>
      state.currentUser?.display_name || state.currentUser?.email || 'Anonymous',
  },

  actions: {
    async bootstrap() {
      if (this.isReady) {
        return
      }

      const storedToken = window.localStorage.getItem('kuboard:token')
      if (!storedToken) {
        this.isReady = true
        return
      }

      this.token = storedToken
      try {
        this.currentUser = await apiRequest<UserProfile>('/api/v1/me')
      } catch {
        this.reset()
      } finally {
        this.isReady = true
      }
    },

    async login(email: string, password: string) {
      this.isAuthenticating = true
      try {
        const response = await apiRequest<LoginResponse>('/api/v1/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
          skipAuth: true,
        })

        this.token = response.token
        this.currentUser = response.user
        setStoredToken(response.token)
      } finally {
        this.isAuthenticating = false
        this.isReady = true
      }
    },

    async logout() {
      try {
        await apiRequest('/api/v1/auth/logout', { method: 'POST' })
      } finally {
        this.reset()
      }
    },

    reset() {
      this.token = ''
      this.currentUser = null
      this.isReady = true
      clearStoredToken()
    },
  },
})

