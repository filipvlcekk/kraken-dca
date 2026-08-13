import { describe, expect, it, vi } from 'vitest'

import type { ApiResponse, HistoryResponse } from '../api'
import { createHistoryStore } from '../historyStore'

const historyResponse: HistoryResponse = {
  entries: [],
  pairs: [
    {
      pair: 'XXBTZEUR',
      trade_count: 2,
      total_volume: '0.02',
      total_spent: '50.10',
      total_price: '50',
      total_fees: '0.10',
      average_buy_price: '2500',
      last_trade_at: '2026-07-21T08:00:00',
      last_trade_txid: 'TXID',
      current_price: '3000',
      estimated_value: '60',
      estimated_pl: '9.90',
    },
  ],
  portfolio: {
    trade_count: 2,
    total_spent: '50.10',
    total_price: '50',
    total_fees: '0.10',
    estimated_value: '60',
    estimated_pl: '9.90',
  },
  chart: [],
  valuation: {
    status: 'live',
    message: null,
  },
}

describe('history store', () => {
  it('loads history and clears stale errors', async () => {
    const loadHistory = vi.fn<() => Promise<ApiResponse<HistoryResponse>>>().mockResolvedValue({
      ok: true,
      data: historyResponse,
    })
    const store = createHistoryStore({ loadHistory })
    store.state.error = 'previous failure'

    const loaded = await store.load()

    expect(loaded).toBe(true)
    expect(loadHistory).toHaveBeenCalledOnce()
    expect(store.state.history).toEqual(historyResponse)
    expect(store.state.error).toBeNull()
    expect(store.state.loading).toBe(false)
  })

  it('surfaces load errors without clearing existing history', async () => {
    const loadHistory = vi.fn<() => Promise<ApiResponse<HistoryResponse>>>().mockResolvedValue({
      ok: false,
      error: {
        code: 'history_read_failed',
        message: 'Order history could not be read.',
      },
    })
    const store = createHistoryStore({ loadHistory })
    store.state.history = historyResponse

    const loaded = await store.load()

    expect(loaded).toBe(false)
    expect(store.state.history).toEqual(historyResponse)
    expect(store.state.error).toBe('Order history could not be read.')
    expect(store.state.loading).toBe(false)
  })
})
