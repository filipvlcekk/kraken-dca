import { reactive } from 'vue'

import {
  loadSchedulerStatus,
  reloadScheduler,
  runPairNow as apiRunPairNow,
  type ApiResponse,
  type RunResult,
  type SchedulerStatus,
} from './api'

export type ManualRunStatus =
  | 'running'
  | 'completed'
  | 'skipped'
  | 'running-conflict'
  | 'failed'

export type ManualRunState = {
  status: ManualRunStatus
  message: string
  reason?: string | null
  orderTxid?: string | null
}

export type SchedulerStoreState = {
  status: SchedulerStatus | null
  loading: boolean
  reloading: boolean
  loadError: string | null
  reloadError: string | null
  manualRuns: Record<string, ManualRunState | undefined>
}

type SchedulerStoreApi = {
  loadSchedulerStatus: () => Promise<ApiResponse<SchedulerStatus>>
  reloadScheduler: (csrfToken: string) => Promise<ApiResponse<{ scheduler: SchedulerStatus }>>
  runPairNow: (pair: string, csrfToken: string) => Promise<ApiResponse<RunResult>>
}

export function createSchedulerStore(api: Partial<SchedulerStoreApi> = {}) {
  const client: SchedulerStoreApi = {
    loadSchedulerStatus: api.loadSchedulerStatus ?? loadSchedulerStatus,
    reloadScheduler: api.reloadScheduler ?? reloadScheduler,
    runPairNow: api.runPairNow ?? apiRunPairNow,
  }
  const state = reactive<SchedulerStoreState>({
    status: null,
    loading: false,
    reloading: false,
    loadError: null,
    reloadError: null,
    manualRuns: {},
  })

  async function loadStatus(): Promise<boolean> {
    state.loading = true
    try {
      const response = await client.loadSchedulerStatus()
      if (!response.ok) {
        state.loadError = response.error.message
        return false
      }
      state.status = response.data
      state.loadError = null
      return true
    } finally {
      state.loading = false
    }
  }

  async function reload(csrfToken: string): Promise<boolean> {
    state.reloading = true
    try {
      const response = await client.reloadScheduler(csrfToken)
      if (!response.ok) {
        state.reloadError = response.error.message
        return false
      }
      state.status = response.data.scheduler
      state.reloadError = null
      return true
    } finally {
      state.reloading = false
    }
  }

  async function runPairNow(pair: string, csrfToken: string): Promise<boolean> {
    state.manualRuns[pair] = {
      status: 'running',
      message: 'Manual run started.',
    }
    const response = await client.runPairNow(pair, csrfToken)
    if (!response.ok) {
      state.manualRuns[pair] = manualRunErrorState(response.error.code, response.error.message)
      return false
    }
    state.manualRuns[pair] = manualRunSuccessState(response.data)
    return true
  }

  return {
    state,
    loadStatus,
    reload,
    runPairNow,
  }
}

function manualRunSuccessState(result: RunResult): ManualRunState {
  const status: ManualRunStatus = result.status === 'success'
    ? 'completed'
    : result.status

  return {
    status,
    message: result.message,
    reason: result.reason,
    orderTxid: result.order_txid,
  }
}

function manualRunErrorState(code: string, message: string): ManualRunState {
  if (code === 'manual_run_already_running') {
    return {
      status: 'running-conflict',
      message,
    }
  }
  return {
    status: 'failed',
    message,
  }
}
