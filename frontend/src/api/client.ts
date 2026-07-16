// Dünner Client über die FastAPI-Prüf-API. Eine Origin via Vite-Proxy (/api).

export interface CheckResult {
  results: Record<string, unknown>[]
  files_checked: number
  result_count: number
  duration_ms: number
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* keine JSON-Antwort */ }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  get: <T>(path: string) => request<T>(path),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form, headers: {} }),
}

export interface Dataset {
  directory: string
  file_count: number
  files: { subdir: string; filename: string; size_kb: number }[]
  session_id?: string | null
  errors?: string[]
}

export interface Datasource { name: string; path: string; key: string; exists: boolean }

export const dataApi = {
  datasources: () => api.get<Datasource[]>('/data/datasources'),
  scan: (directory: string) => api.post<Dataset>('/data/scan', { directory }),
  upload: (files: File[], sessionId?: string) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const q = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
    return api.upload<Dataset>(`/data/upload${q}`, form)
  },
}

export interface ValidatorResponse {
  wellformed: Record<string, unknown>[]
  schema_errors: Record<string, unknown>[]
  files_checked: number
  files_with_wellformed_errors: number
  files_with_schema_errors: number
  duration_ms: number
}
