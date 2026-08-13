import { reactive } from 'vue'

import {
  loadHistory,
  type ApiResponse,
  type HistoryResponse,
} from './api'

export type HistoryStoreState = {
  history: HistoryResponse | null
  loading: boolean
  error: string | null
}

type HistoryStoreApi = {
  loadHistory: () => Promise<ApiResponse<HistoryResponse>>
}

export function createHistoryStore(api: Partial<HistoryStoreApi> = {}) {
  const client: HistoryStoreApi = {
    loadHistory: api.loadHistory ?? loadHistory,
  }
  const state = reactive<HistoryStoreState>({
    history: null,
    loading: false,
    error: null,
  })

  async function load(): Promise<boolean> {
    state.loading = true
    try {
      const response = await client.loadHistory()
      if (!response.ok) {
        state.error = response.error.message
        return false
      }
      state.history = response.data
      state.error = null
      return true
    } finally {
      state.loading = false
    }
  }

  return {
    state,
    load,
  }
}
