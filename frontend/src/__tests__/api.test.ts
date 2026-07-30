import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  REDACTED_SECRET,
  loadConfig,
  loadSchedulerStatus,
  login,
  logout,
  reloadScheduler,
  restoreSession,
  runPairNow,
  saveConfig,
  searchAssetPairs,
  type AppConfig,
} from '../api'

describe('API client', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('exposes session, config, scheduler, and manual run helpers', () => {
    expect(restoreSession).toBeTypeOf('function')
    expect(login).toBeTypeOf('function')
    expect(logout).toBeTypeOf('function')
    expect(loadConfig).toBeTypeOf('function')
    expect(saveConfig).toBeTypeOf('function')
    expect(loadSchedulerStatus).toBeTypeOf('function')
    expect(reloadScheduler).toBeTypeOf('function')
    expect(runPairNow).toBeTypeOf('function')
    expect(searchAssetPairs).toBeTypeOf('function')
  })

  it('attaches X-CSRF-Token on unsafe requests', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true, data: { scheduler: { running: true } } }))

    await reloadScheduler('csrf-token')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/scheduler/reload',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-CSRF-Token': 'csrf-token',
        }),
      }),
    )
  })

  it('uses expected endpoint methods and payloads', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ ok: true, data: { authenticated: true } })))
    await login('secret')
    await logout('csrf-token')
    await restoreSession()

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/session',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ password: 'secret' }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/session',
      expect.objectContaining({
        method: 'DELETE',
        headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-token' }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/session',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('loads config, scheduler status, and manual run endpoints', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ ok: true, data: {} })))

    await loadConfig()
    await loadSchedulerStatus()
    await runPairNow('XXBT/ZEUR', 'csrf-token')

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/config', expect.objectContaining({ method: 'GET' }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/scheduler', expect.objectContaining({ method: 'GET' }))
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/pairs/XXBT%2FZEUR/run',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-token' }),
      }),
    )
  })

  it('searches asset pairs with an encoded query string', async () => {
    fetchMock.mockResolvedValue(jsonResponse({
      ok: true,
      data: {
        pairs: [
          {
            pair: 'XXBTZEUR',
            altname: 'XBTEUR',
            wsname: 'XBT/EUR',
          },
        ],
      },
    }))

    const response = await searchAssetPairs('XBT/EUR')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/asset-pairs?q=XBT%2FEUR',
      expect.objectContaining({ method: 'GET' }),
    )
    expect(response).toEqual({
      ok: true,
      data: [
        {
          pair: 'XXBTZEUR',
          altname: 'XBTEUR',
          wsname: 'XBT/EUR',
        },
      ],
    })
  })

  it('saves config using the backend payload shape and preserves redacted secrets', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true, data: { config_valid: true } }))
    const config: AppConfig = {
      api: {
        public_key: REDACTED_SECRET,
        private_key: REDACTED_SECRET,
      },
      dca_pairs: [
        {
          pair: 'XETHZEUR',
          amount: 15,
          schedule: {
            cron: '0 9 * * *',
            timezone: 'Europe/Prague',
          },
        },
      ],
    }

    await saveConfig(config, 'csrf-token')

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(fetchMock).toHaveBeenCalledWith('/api/config', expect.objectContaining({ method: 'PUT' }))
    expect(request.headers).toMatchObject({
      'Content-Type': 'application/json',
      'X-CSRF-Token': 'csrf-token',
    })
    expect(JSON.parse(String(request.body))).toEqual({
      config: {
        api: {
          public_key: REDACTED_SECRET,
          private_key: REDACTED_SECRET,
        },
        dca_pairs: [
          {
            pair: 'XETHZEUR',
            amount: 15,
            schedule: {
              enabled: true,
              cron: '0 9 * * *',
              timezone: 'Europe/Prague',
            },
          },
        ],
      },
    })
  })

  it('round-trips env-backed credentials as null or omitted without inventing sentinels', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true, data: { config_valid: true } }))
    const config: AppConfig = {
      api: {
        public_key: null,
      },
      dca_pairs: [
        {
          pair: 'XXBTZEUR',
          amount: 20,
          schedule: {
            enabled: false,
          },
        },
      ],
    }

    await saveConfig(config, 'csrf-token')

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(JSON.parse(String(request.body))).toEqual({
      config: {
        api: {
          public_key: null,
        },
        dca_pairs: [
          {
            pair: 'XXBTZEUR',
            amount: 20,
            schedule: {
              enabled: false,
            },
          },
        ],
      },
    })
    expect(String(request.body)).not.toContain(REDACTED_SECRET)
  })

  it('surfaces backend error envelopes unchanged', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        ok: false,
        error: {
          code: 'validation_error',
          message: 'Invalid config.',
          fields: { 'dca_pairs.0.amount': 'Amount is required.' },
        },
      }),
    )

    const response = await saveConfig({ dca_pairs: [] }, 'csrf-token')

    expect(response).toEqual({
      ok: false,
      error: {
        code: 'validation_error',
        message: 'Invalid config.',
        fields: { 'dca_pairs.0.amount': 'Amount is required.' },
      },
    })
  })
})

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}
