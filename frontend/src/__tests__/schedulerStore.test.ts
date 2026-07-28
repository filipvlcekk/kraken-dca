import { describe, expect, it, vi } from 'vitest'

import type {
  ApiResponse,
  RunResult,
  SchedulerStatus,
} from '../api'
import { createSchedulerStore } from '../schedulerStore'

const schedulerStatus: SchedulerStatus = {
  running: true,
  config_applied: true,
  saved_config_fingerprint: 'saved',
  active_config_fingerprint: 'active',
  reload_error: null,
  last_reload_at: '2026-07-21T08:00:00Z',
  jobs: [
    {
      id: 'XXBTZEUR',
      pair: 'XXBTZEUR',
      mode: 'cron',
      enabled: true,
      cron: '0 9 * * *',
      timezone: 'Europe/Prague',
      next_run_at: '2026-07-22T07:00:00Z',
      running: false,
    },
  ],
}

describe('scheduler store', () => {
  it('loads scheduler status and clears stale load errors', async () => {
    const loadSchedulerStatus = vi.fn<() => Promise<ApiResponse<SchedulerStatus>>>().mockResolvedValue({
      ok: true,
      data: schedulerStatus,
    })
    const store = createSchedulerStore({
      loadSchedulerStatus,
      reloadScheduler: vi.fn(),
      runPairNow: vi.fn(),
    })
    store.state.loadError = 'previous failure'

    const loaded = await store.loadStatus()

    expect(loaded).toBe(true)
    expect(loadSchedulerStatus).toHaveBeenCalledOnce()
    expect(store.state.status).toEqual(schedulerStatus)
    expect(store.state.loadError).toBeNull()
    expect(store.state.loading).toBe(false)
  })

  it('reloads the scheduler and surfaces reload errors', async () => {
    const reloadScheduler = vi.fn().mockResolvedValue({
      ok: true,
      data: { scheduler: { ...schedulerStatus, running: false } },
    })
    const store = createSchedulerStore({
      loadSchedulerStatus: vi.fn(),
      reloadScheduler,
      runPairNow: vi.fn(),
    })

    const reloaded = await store.reload('csrf-token')

    expect(reloaded).toBe(true)
    expect(reloadScheduler).toHaveBeenCalledWith('csrf-token')
    expect(store.state.status?.running).toBe(false)
    expect(store.state.reloadError).toBeNull()

    reloadScheduler.mockResolvedValueOnce({
      ok: false,
      error: {
        code: 'scheduler_reload_failed',
        message: 'Invalid cron expression.',
      },
    })

    const failed = await store.reload('csrf-token')

    expect(failed).toBe(false)
    expect(store.state.reloadError).toBe('Invalid cron expression.')
    expect(store.state.reloading).toBe(false)
  })

  it('tracks manual run state by pair from running through completion', async () => {
    let resolveRun: (response: ApiResponse<RunResult>) => void = () => {}
    const runPairNow = vi.fn(() => new Promise<ApiResponse<RunResult>>((resolve) => {
      resolveRun = resolve
    }))
    const store = createSchedulerStore({
      loadSchedulerStatus: vi.fn(),
      reloadScheduler: vi.fn(),
      runPairNow,
    })

    const runTask = store.runPairNow('XXBTZEUR', 'csrf-token')

    expect(runPairNow).toHaveBeenCalledWith('XXBTZEUR', 'csrf-token')
    expect(store.state.manualRuns.XXBTZEUR).toEqual({
      status: 'running',
      message: 'Manual run started.',
    })

    resolveRun({
      ok: true,
      data: {
        pair: 'XXBTZEUR',
        status: 'skipped',
        reason: 'min_order_interval',
        started_at: '2026-07-21T08:00:00Z',
        finished_at: '2026-07-21T08:00:01Z',
        order_txid: null,
        message: 'Skipped because the pair ran recently.',
      },
    })

    expect(await runTask).toBe(true)
    expect(store.state.manualRuns.XXBTZEUR).toEqual({
      status: 'skipped',
      message: 'Skipped because the pair ran recently.',
      reason: 'min_order_interval',
      orderTxid: null,
    })
  })

  it('maps running-conflict manual run errors without clearing other pair state', async () => {
    const store = createSchedulerStore({
      loadSchedulerStatus: vi.fn(),
      reloadScheduler: vi.fn(),
      runPairNow: vi.fn().mockResolvedValue({
        ok: false,
        error: {
          code: 'manual_run_already_running',
          message: 'A run is already active for this pair.',
        },
      }),
    })
    store.state.manualRuns.XETHZEUR = {
      status: 'completed',
      message: 'Previous run completed.',
      orderTxid: 'ORDER-1',
    }

    const ran = await store.runPairNow('XXBTZEUR', 'csrf-token')

    expect(ran).toBe(false)
    expect(store.state.manualRuns.XXBTZEUR).toEqual({
      status: 'running-conflict',
      message: 'A run is already active for this pair.',
    })
    expect(store.state.manualRuns.XETHZEUR?.status).toBe('completed')
  })
})
