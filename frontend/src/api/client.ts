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
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
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

export interface DbLetterSummary { letter: string; article_count: number }
export interface DbResourceSummary { resource_id: string; article_count: number; letters: DbLetterSummary[] }
export interface DbArticleSummary { source_path: string; article_id: string; lemma: string | null; pos: string | null }
export interface DbSearchHit { resource_id: string; letter: string; source_path: string; article_id: string; lemma: string | null }
export interface DbSelection {
  resource_ids: string[]
  resource_letters: [string, string][]
  articles: [string, string][]
}

export interface LoadJobHandle { job_id: string; total: number }
export interface LoadJobStatus {
  status: 'running' | 'ok' | 'error'
  done: number
  total: number
  error: string | null
  result: Dataset | null
}

export interface User { id: number; username: string; wbdb_principal_id: string | null; is_admin: boolean }

export const authApi = {
  login: (username: string, password: string) => api.post<User>('/auth/login', { username, password }),
  logout: () => api.post<{ status: string }>('/auth/logout', {}),
  me: () => api.get<User>('/auth/me'),
}

export interface AdminUser {
  id: number
  username: string
  wbdb_principal_id: string | null
  is_admin: boolean
  active: boolean
  created_at: string
}

export interface ScopeResult {
  principal_id: string
  scope: Record<string, unknown>[]
}

export interface Principal {
  principal_id: string
  kind: string
  label: string
  active: boolean
}

export interface WbdbIndexStatus {
  build_id: number | null
  started_at: string | null
  finished_at: string | null
  status: string | null
  row_count: number | null
  error: string | null
  triggered_by: string | null
}

export const adminApi = {
  listUsers: () => api.get<AdminUser[]>('/admin/users'),
  listPrincipals: () => api.get<Principal[]>('/admin/principals'),
  createUser: (username: string, password: string, wbdbPrincipalId: string, isAdmin: boolean) =>
    api.post<AdminUser>('/admin/users', {
      username, password, wbdb_principal_id: wbdbPrincipalId || null, is_admin: isAdmin,
    }),
  updateUser: (id: number, patch: { wbdb_principal_id?: string | null; is_admin?: boolean; active?: boolean }) =>
    api.patch<AdminUser>(`/admin/users/${id}`, patch),
  resetPassword: (id: number, password: string) =>
    api.post<{ status: string }>(`/admin/users/${id}/password`, { password }),
  testPrincipal: (principalId: string) =>
    api.post<ScopeResult>('/admin/test-principal', { principal_id: principalId }),
  wbdbIndexStatus: () => api.get<WbdbIndexStatus>('/admin/wbdb-index/status'),
  rebuildWbdbIndex: () => api.post<WbdbIndexStatus>('/admin/wbdb-index/rebuild', {}),
}

export const dataApi = {
  datasources: () => api.get<Datasource[]>('/data/datasources'),
  scan: (directory: string) => api.post<Dataset>('/data/scan', { directory }),
  upload: (files: File[], sessionId?: string) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const q = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
    return api.upload<Dataset>(`/data/upload${q}`, form)
  },
  dbIndexTree: () => api.get<DbResourceSummary[]>('/data/db-index/tree'),
  dbIndexLetter: (resourceId: string, letter: string) =>
    api.get<DbArticleSummary[]>(
      `/data/db-index/letter?resource_id=${encodeURIComponent(resourceId)}&letter=${encodeURIComponent(letter)}`
    ),
  dbIndexSearch: (q: string) => api.get<DbSearchHit[]>(`/data/db-index/search?q=${encodeURIComponent(q)}`),
  dbIndexSearchFiles: (q: string, resourceIds: string[] = []) => {
    const params = new URLSearchParams({ q })
    for (const id of resourceIds) params.append('resource_ids', id)
    return api.get<DbSearchHit[]>(`/data/db-index/search-files?${params.toString()}`)
  },
  dbIndexArticle: (resourceId: string, sourcePath: string) =>
    api.get<{ content: string }>(
      `/data/db-index/article?resource_id=${encodeURIComponent(resourceId)}&source_path=${encodeURIComponent(sourcePath)}`
    ),
  dbLoadSelection: (selection: DbSelection) => api.post<LoadJobHandle>('/data/db-load', selection),
  dbLoadStatus: (jobId: string) => api.get<LoadJobStatus>(`/data/db-load/${jobId}`),
  fileContent: (directory: string, subdir: string, filename: string) =>
    api.get<{ content: string }>(
      `/data/file-content?directory=${encodeURIComponent(directory)}&subdir=${encodeURIComponent(subdir)}&filename=${encodeURIComponent(filename)}`
    ),
}

export interface JobStatus<T> {
  status: 'running' | 'ok' | 'error'
  phase: string
  done: number
  total: number
  error: string | null
  result: T | null
}

/** Job starten (POST liefert {job_id,...}) und `statusPath` pollen, bis der
 *  Job fertig ist — Basis für jede job-basierte Prüfung (siehe `registry.ts`
 *  `runJob`). `onProgress` wird bei jedem Poll aufgerufen. */
export async function pollJob<T>(
  statusPath: string,
  onProgress: (p: { phase: string; done: number; total: number }) => void,
  intervalMs = 800,
): Promise<T> {
  for (;;) {
    const s = await api.get<JobStatus<T>>(statusPath)
    onProgress({ phase: s.phase, done: s.done, total: s.total })
    if (s.status === 'ok') return s.result as T
    if (s.status === 'error') throw new ApiError(500, s.error ?? 'Prüfung fehlgeschlagen.')
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}

export interface ValidatorResponse {
  wellformed: Record<string, unknown>[]
  schema_errors: Record<string, unknown>[]
  files_checked: number
  files_with_wellformed_errors: number
  files_with_schema_errors: number
  duration_ms: number
}
