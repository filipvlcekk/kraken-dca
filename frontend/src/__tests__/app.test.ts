import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App.vue'
import { createAuthStore } from '../authStore'

const emptySecrets = {
  public_key: { configured: false, source: null },
  private_key: { configured: false, source: null },
} as const

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
      },
    }))
    const store = createAuthStore()

    const restored = await store.restore()

    expect(restored).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/session', expect.objectContaining({ method: 'GET' }))
    expect(store.state.authenticated).toBe(true)
    expect(store.state.csrfToken).toBe('csrf-token')
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
      },
    }))

    const wrapper = mount(App)
    await flushDashboard()

    expect(wrapper.text()).toContain('Sign in to Kraken DCA')
    expect(wrapper.find('input[aria-label="Web UI password"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Authenticated dashboard')
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
      return Promise.resolve(jsonResponse({ ok: true, data: {} }))
    })

    const wrapper = mount(App)
    await flushDashboard()

    expect(wrapper.text()).toContain('Authenticated dashboard')
    expect(wrapper.text()).toContain('XXBTZEUR')
    expect(wrapper.text()).toContain('Scheduler running')
    expect(wrapper.text()).toContain('Add pair')
    expect(wrapper.text()).toContain('Save config')
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
