type RequestOptions = RequestInit & {
  skipAuth?: boolean
}

class ApiError extends Error {
  status: number
  details: unknown

  constructor(message: string, status: number, details?: unknown) {
    super(message)
    this.status = status
    this.details = details
  }
}

const TOKEN_STORAGE_KEY = 'kuboard:token'
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export function getStoredToken() {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function setStoredToken(token: string) {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function clearStoredToken() {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY)
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const body = options.body
  const token = getStoredToken()

  if (!options.skipAuth && token) {
    headers.set('Authorization', `Token ${token}`)
  }

  if (body && !(body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (response.status === 204) {
    return null as T
  }

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(
      payload?.message ?? '请求失败，请稍后再试。',
      response.status,
      payload,
    )
  }

  return payload as T
}

export { ApiError }
