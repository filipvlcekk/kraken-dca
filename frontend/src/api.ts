export const REDACTED_SECRET = '__KRADCA_SECRET_REDACTED__'

export type ApiSuccess<T> = {
  ok: true
  data: T
}

export type ApiError = {
  code: string
  message: string
  fields?: Record<string, string>
  details?: unknown
}

export type ApiResponse<T> = ApiSuccess<T> | {
  ok: false
  error: ApiError
}

export type SecretMetadata = {
  configured: boolean
  source: 'file' | 'env' | null
}

export type DcaPairSchedule = {
  enabled?: boolean
  cron?: string
  timezone?: string
}

export type DcaPairConfig = {
  pair: string
  amount: number
  delay?: number
  schedule?: DcaPairSchedule
  min_order_interval_minutes?: number
  limit_factor?: number
  max_price?: number
  ignore_differing_orders?: boolean
}

export type AssetPairSuggestion = {
  pair: string
  altname?: string
  wsname?: string
  base?: string
  quote?: string
}

export type AppConfig = {
  api?: {
    public_key?: string | null
    private_key?: string | null
  }
  dca_pairs?: DcaPairConfig[]
}

export type ConfigResponse = {
  config: AppConfig
  secrets: {
    public_key: SecretMetadata
    private_key: SecretMetadata
  }
  config_valid: boolean
  validation_errors: Record<string, string>
  raw_yaml?: string | null
}

export type SchedulerJob = {
  id: string
  pair: string
  mode: 'cron' | 'legacy-delay'
  enabled: boolean
  cron: string | null
  timezone: string
  next_run_at: string | null
  running: boolean
}

export type SchedulerStatus = {
  running: boolean
  config_applied: boolean
  saved_config_fingerprint: string | null
  active_config_fingerprint: string | null
  reload_error: string | null
  last_reload_at: string | null
  jobs: SchedulerJob[]
}

export type HistoryEntry = {
  date: string
  pair: string
  type: string
  order_type: string
  o_flags: string
  pair_price: string
  volume: string
  price: string
  fee: string
  total_price: string
  txid: string
  description: string
}

export type PairHistorySummary = {
  pair: string
  trade_count: number
  total_volume: string
  total_spent: string
  total_price: string
  total_fees: string
  average_buy_price: string | null
  last_trade_at: string | null
  last_trade_txid: string | null
  current_price: string | null
  estimated_value: string | null
  estimated_pl: string | null
}

export type PortfolioHistorySummary = {
  trade_count: number
  total_spent: string
  total_price: string
  total_fees: string
  estimated_value: string | null
  estimated_pl: string | null
}

export type HistoryChartPoint = {
  date: string
  pair: string
  txid: string
  spent: string
  volume: string
  cumulative_spent: string
  cumulative_volume: string
}

export type HistoryValuationStatus = {
  status: 'live' | 'unavailable' | 'not_available'
  message: string | null
}

export type HistoryResponse = {
  entries: HistoryEntry[]
  pairs: PairHistorySummary[]
  portfolio: PortfolioHistorySummary
  chart: HistoryChartPoint[]
  valuation: HistoryValuationStatus
}

export type RunResult = {
  pair: string
  status: 'completed' | 'skipped' | 'failed' | 'success'
  reason: string | null
  started_at: string
  finished_at: string
  order_txid: string | null
  message: string
}

export type SessionResponse = {
  authenticated: boolean
  auth_mode?: 'password' | 'oidc'
  oidc_login_url?: string
  csrf_token?: string
}

export type SaveConfigResponse = ConfigResponse & {
  scheduler: SchedulerStatus
}

export function restoreSession(): Promise<ApiResponse<SessionResponse>> {
  return request('/api/session')
}

export function login(password: string): Promise<ApiResponse<SessionResponse>> {
  return request('/api/session', {
    method: 'POST',
    body: { password },
  })
}

export function logout(csrfToken: string): Promise<ApiResponse<SessionResponse>> {
  return request('/api/session', {
    method: 'DELETE',
    csrfToken,
  })
}

export function loadConfig(): Promise<ApiResponse<ConfigResponse>> {
  return request('/api/config')
}

export function loadHistory(): Promise<ApiResponse<HistoryResponse>> {
  return request('/api/history')
}

export function saveConfig(
  config: AppConfig,
  csrfToken: string,
): Promise<ApiResponse<SaveConfigResponse>> {
  return request('/api/config', {
    method: 'PUT',
    csrfToken,
    body: { config: normalizeConfigForSave(config) },
  })
}

export function loadSchedulerStatus(): Promise<ApiResponse<SchedulerStatus>> {
  return request('/api/scheduler')
}

export function reloadScheduler(csrfToken: string): Promise<ApiResponse<{ scheduler: SchedulerStatus }>> {
  return request('/api/scheduler/reload', {
    method: 'POST',
    csrfToken,
  })
}

export function runPairNow(
  pair: string,
  csrfToken: string,
): Promise<ApiResponse<RunResult>> {
  return request(`/api/pairs/${encodeURIComponent(pair)}/run`, {
    method: 'POST',
    csrfToken,
  })
}

export async function searchAssetPairs(
  q: string,
): Promise<ApiResponse<AssetPairSuggestion[]>> {
  const response = await request<{ pairs: AssetPairSuggestion[] }>(
    `/api/asset-pairs?q=${encodeURIComponent(q)}`,
  )
  if (!response.ok) {
    return response
  }
  return {
    ok: true,
    data: response.data.pairs,
  }
}

type RequestOptions = {
  method?: string
  csrfToken?: string
  body?: unknown
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<ApiResponse<T>> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = {}
  let body: string | undefined

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  if (options.csrfToken) {
    headers['X-CSRF-Token'] = options.csrfToken
  }

  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers,
    body,
  })
  return await response.json() as ApiResponse<T>
}

function normalizeConfigForSave(config: AppConfig): AppConfig {
  return {
    ...config,
    dca_pairs: (config.dca_pairs ?? []).map((pair) => {
      if (pair.schedule === undefined) {
        return pair
      }
      if (pair.schedule.enabled !== undefined || pair.schedule.cron === undefined) {
        return {
          ...pair,
          schedule: { ...pair.schedule },
        }
      }
      return {
        ...pair,
        schedule: {
          ...pair.schedule,
          enabled: true,
        },
      }
    }),
  }
}
