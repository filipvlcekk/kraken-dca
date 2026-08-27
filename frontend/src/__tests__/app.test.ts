import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App.vue'
import { createAuthStore } from '../authStore'

const emptySecrets = {
  public_key: { configured: false, source: null },
  private_key: { configured: false, source: null },
} as const

const emptyHistory = {
  entries: [],
  pairs: [],
  portfolio: {
    trade_count: 0,
    total_spent: '0',
    total_price: '0',
    total_fees: '0',
    estimated_value: null,
    estimated_pl: null,
  },
  chart: [],
  valuation: {
    status: 'not_available',
    message: null,
  },
}

describe('auth store', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('restores session through GET /api/session', async () => {
    fetchMock.mockResolvedValue(jsonResponse({
      ok: true,
      data: {
        authenticated: true,
        csrf_token: 'csrf-token',
        auth_mode: 'password',
      },
    }))
    const store = createAuthStore()

    const restored = await store.restore()

    expect(restored).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/session', expect.objectContaining({ method: 'GET' }))
    expect(store.state.authenticated).toBe(true)
    expect(store.state.csrfToken).toBe('csrf-token')
    expect(store.state.authMode).toBe('password')
  })

  it('stores OIDC login capabilities from session restore', async () => {
    fetchMock.mockResolvedValue(jsonResponse({
      ok: true,
      data: {
        authenticated: false,
        auth_mode: 'oidc',
        oidc_login_url: '/api/auth/oidc/start',
      },
    }))
    const store = createAuthStore()

    const restored = await store.restore()

    expect(restored).toBe(false)
    expect(store.state.authenticated).toBe(false)
    expect(store.state.authMode).toBe('oidc')
    expect(store.state.oidcLoginUrl).toBe('/api/auth/oidc/start')
  })
})

describe('App shell', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the login shell when unauthenticated', async () => {
    fetchMock.mockResolvedValue(jsonResponse({
      ok: true,
      data: {
        authenticated: false,
        auth_mode: 'password',
      },
    }))

    const wrapper = mount(App)
    await flushDashboard()

    expect(wrapper.text()).toContain('Sign in to Kraken DCA')
    expect(wrapper.find('input[aria-label="Web UI password"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Authenticated dashboard')
  })

  it('renders OIDC-only login and redirects to Pocket ID start', async () => {
    const location = { href: 'https://testserver/login' }
    vi.stubGlobal('location', location)
    fetchMock.mockResolvedValue(jsonResponse({
      ok: true,
      data: {
        authenticated: false,
        auth_mode: 'oidc',
        oidc_login_url: '/api/auth/oidc/start',
      },
    }))

    const wrapper = mount(App)
    await flushDashboard()

    expect(wrapper.find('input[aria-label="Web UI password"]').exists()).toBe(false)
    await wrapper.get('button[type="button"]').trigger('click')

    expect(location.href).toBe('/api/auth/oidc/start')
  })

  it('renders the authenticated dashboard after session restore', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/session') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            authenticated: true,
            csrf_token: 'csrf-token',
          },
        }))
      }
      if (path === '/api/config') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            config: {
              dca_pairs: [
                {
                  pair: 'XXBTZEUR',
                  amount: 15,
                  schedule: {
                    enabled: true,
                    cron: '0 9 * * *',
                    timezone: 'Europe/Prague',
                  },
                  min_order_interval_minutes: 30,
                },
              ],
            },
            secrets: emptySecrets,
            config_valid: true,
            validation_errors: {},
          },
        }))
      }
      if (path === '/api/scheduler') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            running: true,
            config_applied: true,
            saved_config_fingerprint: 'saved',
            active_config_fingerprint: 'active',
            reload_error: null,
            last_reload_at: '2026-07-21T08:00:00Z',
            jobs: [],
          },
        }))
      }
      if (path === '/api/history') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            entries: [
              {
                date: '2026-07-21T10:00:00',
                pair: 'XXBTZEUR',
                type: 'buy',
                order_type: 'limit',
                o_flags: 'fciq',
                pair_price: '2500',
                volume: '0.02',
                price: '50',
                fee: '0.10',
                total_price: '50.10',
                txid: 'TXID',
                description: 'buy 0.02 XXBTZEUR @ limit 2500',
              },
            ],
            pairs: [
              {
                pair: 'XXBTZEUR',
                trade_count: 1,
                total_volume: '0.02',
                total_spent: '50.10',
                total_price: '50',
                total_fees: '0.10',
                average_buy_price: '2500',
                last_trade_at: '2026-07-21T10:00:00',
                last_trade_txid: 'TXID',
                current_price: '3000',
                estimated_value: '60',
                estimated_pl: '9.90',
              },
            ],
            portfolio: {
              trade_count: 1,
              total_spent: '50.10',
              total_price: '50',
              total_fees: '0.10',
              estimated_value: '60',
              estimated_pl: '9.90',
            },
            chart: [
              {
                date: '2026-07-21T10:00:00',
                pair: 'XXBTZEUR',
                txid: 'TXID',
                spent: '50.10',
                volume: '0.02',
                cumulative_spent: '50.10',
                cumulative_volume: '0.02',
              },
            ],
            valuation: {
              status: 'live',
              message: null,
            },
          },
        }))
      }
      return Promise.resolve(jsonResponse({ ok: true, data: {} }))
    })

    const wrapper = mount(App)
    await flushDashboard()

    expect(wrapper.text()).toContain('Authenticated dashboard')
    expect(wrapper.text()).toContain('XXBTZEUR')
    expect(wrapper.text()).toContain('Scheduler running')
    expect(wrapper.text()).toContain('You spent')
    expect(wrapper.text()).toContain('Completed order history')
    expect(wrapper.text()).toContain('Add pair')
    expect(wrapper.text()).toContain('Save config')
  })

  it('refreshes order history after importing selected orders', async () => {
    const readyTxid = 'ABC123-DEFGH-IJKLMN'
    const historyRequests: string[] = []
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/session') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            authenticated: true,
            csrf_token: 'csrf-token',
          },
        }))
      }
      if (path === '/api/config') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            config: {
              dca_pairs: [],
            },
            secrets: emptySecrets,
            config_valid: true,
            validation_errors: {},
          },
        }))
      }
      if (path === '/api/scheduler') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            running: true,
            config_applied: true,
            saved_config_fingerprint: 'saved',
            active_config_fingerprint: 'active',
            reload_error: null,
            last_reload_at: null,
            jobs: [],
          },
        }))
      }
      if (path === '/api/history') {
        historyRequests.push(path)
        return Promise.resolve(jsonResponse({
          ok: true,
          data: historyRequests.length === 1
            ? historyWithEntry('OLDTX1-ABCDE-QRSTUV', 'XXBTZEUR', '50.10')
            : historyWithEntry(readyTxid, 'XETHZEUR', '75.25'),
        }))
      }
      if (path === '/api/history/import/preview') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            imported_count: 0,
            skipped_count: 0,
            items: [
              {
                txid: readyTxid,
                status: 'ready',
                message: 'Ready to import.',
                row: null,
                target_file: null,
              },
            ],
          },
        }))
      }
      if (path === '/api/history/import') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            imported_count: 1,
            skipped_count: 0,
            items: [],
          },
        }))
      }
      return Promise.resolve(jsonResponse({ ok: true, data: {} }))
    })

    const wrapper = mount(App)
    await flushDashboard()

    expect(historyRequests).toHaveLength(1)
    expect(wrapper.text()).toContain('XXBTZEUR')

    await wrapper.get('button[aria-label="Import orders"]').trigger('click')
    await wrapper.get('textarea[aria-label="Order transaction ids"]').setValue(readyTxid)
    await wrapper.get('button[aria-label="Preview import"]').trigger('click')
    await flushPromises()
    await wrapper.get(`input[aria-label="Select ${readyTxid}"]`).setValue(true)
    await wrapper.get('button[aria-label="Import selected"]').trigger('click')
    await flushDashboard()

    expect(historyRequests).toHaveLength(2)
    expect(wrapper.text()).toContain('XETHZEUR')
    expect(wrapper.text()).toContain('75.25')
  })

  it('keeps the pair input mounted while editing the pair value', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/session') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            authenticated: true,
            csrf_token: 'csrf-token',
          },
        }))
      }
      if (path === '/api/config') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            config: {
              dca_pairs: [
                {
                  pair: 'XXBTZEUR',
                  amount: 15,
                  schedule: {
                    enabled: true,
                    cron: '0 9 * * *',
                    timezone: 'Europe/Prague',
                  },
                  min_order_interval_minutes: 30,
                },
              ],
            },
            secrets: emptySecrets,
            config_valid: true,
            validation_errors: {},
          },
        }))
      }
      if (path === '/api/scheduler') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            running: true,
            config_applied: true,
            saved_config_fingerprint: 'saved',
            active_config_fingerprint: 'active',
            reload_error: null,
            last_reload_at: null,
            jobs: [],
          },
        }))
      }
      if (path.startsWith('/api/asset-pairs')) {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: { pairs: [] },
        }))
      }
      if (path === '/api/history') {
        return Promise.resolve(jsonResponse({ ok: true, data: emptyHistory }))
      }
      return Promise.resolve(jsonResponse({ ok: true, data: {} }))
    })

    const wrapper = mount(App)
    await flushDashboard()
    const input = wrapper.get<HTMLInputElement>('input[aria-label="Pair name"]')
    const originalElement = input.element

    await input.setValue('X')
    await flushPromises()

    expect(wrapper.get<HTMLInputElement>('input[aria-label="Pair name"]').element)
      .toBe(originalElement)
  })

  it('shows setup and degraded state through config warnings', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/session') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            authenticated: true,
            csrf_token: 'csrf-token',
          },
        }))
      }
      if (path === '/api/config') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            config: {
              dca_pairs: [],
            },
            secrets: emptySecrets,
            config_valid: false,
            validation_errors: {
              config: 'Config file not found.',
            },
          },
        }))
      }
      if (path === '/api/scheduler') {
        return Promise.resolve(jsonResponse({
          ok: true,
          data: {
            running: false,
            config_applied: false,
            saved_config_fingerprint: null,
            active_config_fingerprint: null,
            reload_error: null,
            last_reload_at: null,
            jobs: [],
          },
        }))
      }
      if (path === '/api/history') {
        return Promise.resolve(jsonResponse({ ok: true, data: emptyHistory }))
      }
      return Promise.resolve(jsonResponse({ ok: true, data: {} }))
    })

    const wrapper = mount(App)
    await flushDashboard()

    expect(wrapper.text()).toContain('Setup mode')
    expect(wrapper.text()).toContain('Create and save a valid config.yaml')
  })
})

async function flushDashboard(): Promise<void> {
  await flushPromises()
  await flushPromises()
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function historyWithEntry(txid: string, pair: string, totalPrice: string) {
  return {
    entries: [
      {
        date: '2026-07-21T10:00:00',
        pair,
        type: 'buy',
        order_type: 'limit',
        o_flags: 'fciq',
        pair_price: '2500',
        volume: '0.02',
        price: '50',
        fee: '0.10',
        total_price: totalPrice,
        txid,
        description: `buy 0.02 ${pair} @ limit 2500`,
      },
    ],
    pairs: [
      {
        pair,
        trade_count: 1,
        total_volume: '0.02',
        total_spent: totalPrice,
        total_price: '50',
        total_fees: '0.10',
        average_buy_price: '2500',
        last_trade_at: '2026-07-21T10:00:00',
        last_trade_txid: txid,
        current_price: '3000',
        estimated_value: '60',
        estimated_pl: '9.90',
      },
    ],
    portfolio: {
      trade_count: 1,
      total_spent: totalPrice,
      total_price: '50',
      total_fees: '0.10',
      estimated_value: '60',
      estimated_pl: '9.90',
    },
    chart: [
      {
        date: '2026-07-21T10:00:00',
        pair,
        txid,
        spent: totalPrice,
        volume: '0.02',
        cumulative_spent: totalPrice,
        cumulative_volume: '0.02',
      },
    ],
    valuation: {
      status: 'live',
      message: null,
    },
  }
}
