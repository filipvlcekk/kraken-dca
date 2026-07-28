import { describe, expect, it, vi } from 'vitest'

import {
  REDACTED_SECRET,
  type ApiResponse,
  type ConfigResponse,
  type SaveConfigResponse,
} from '../api'
import { buildConfigSavePayload, createConfigStore } from '../configStore'

const emptySecrets = {
  public_key: { configured: false, source: null },
  private_key: { configured: false, source: null },
} as const

describe('config store', () => {
  it('loads config and secret metadata', async () => {
    const loadConfig = vi.fn<() => Promise<ApiResponse<ConfigResponse>>>().mockResolvedValue({
      ok: true,
      data: {
        config: {
          api: {
            public_key: REDACTED_SECRET,
            private_key: null,
          },
          dca_pairs: [],
        },
        secrets: {
          public_key: { configured: true, source: 'file' },
          private_key: { configured: true, source: 'env' },
        },
        config_valid: true,
        validation_errors: {},
        raw_yaml: null,
      },
    })
    const store = createConfigStore({
      loadConfig,
      saveConfig: vi.fn(),
    })

    await store.load()

    expect(store.state.config.api?.public_key).toBe(REDACTED_SECRET)
    expect(store.state.secrets.private_key).toEqual({ configured: true, source: 'env' })
    expect(store.state.configValid).toBe(true)
    expect(store.state.dirty).toBe(false)
  })

  it('tracks dirty state and field validation errors', async () => {
    const store = createConfigStore({
      loadConfig: vi.fn().mockResolvedValue({
        ok: true,
        data: {
          config: {
            dca_pairs: [{ pair: 'XETHZEUR', amount: 15 }],
          },
          secrets: emptySecrets,
          config_valid: true,
          validation_errors: {},
        },
      }),
      saveConfig: vi.fn().mockResolvedValue({
        ok: false,
        error: {
          code: 'validation_error',
          message: 'Invalid config.',
          fields: { 'dca_pairs.0.amount': 'Amount must be positive.' },
        },
      }),
    })

    await store.load()
    store.updatePair(0, { amount: 0 })
    const saved = await store.save('csrf-token')

    expect(store.state.dirty).toBe(true)
    expect(saved).toBe(false)
    expect(store.state.validationErrors).toEqual({
      'dca_pairs.0.amount': 'Amount must be positive.',
    })
  })

  it('saves normalized payloads through the API client', async () => {
    const saveConfig = vi.fn<() => Promise<ApiResponse<SaveConfigResponse>>>().mockResolvedValue({
      ok: true,
      data: {
        config: { dca_pairs: [] },
        secrets: emptySecrets,
        config_valid: true,
        validation_errors: {},
        scheduler: {
          running: true,
          config_applied: true,
          saved_config_fingerprint: 'saved',
          active_config_fingerprint: 'active',
          reload_error: null,
          last_reload_at: null,
          jobs: [],
        },
      },
    })
    const store = createConfigStore({
      loadConfig: vi.fn(),
      saveConfig,
    })
    store.state.config = {
      dca_pairs: [
        {
          pair: 'XETHZEUR',
          amount: 15,
          schedule: {
            cron: '0 9 * * *',
            timezone: 'UTC',
          },
        },
      ],
    }

    await store.save('csrf-token')

    expect(saveConfig).toHaveBeenCalledWith(
      {
        dca_pairs: [
          {
            pair: 'XETHZEUR',
            amount: 15,
            schedule: {
              enabled: true,
              cron: '0 9 * * *',
              timezone: 'UTC',
            },
          },
        ],
      },
      'csrf-token',
    )
    expect(buildConfigSavePayload({ dca_pairs: [] })).toEqual({
      config: { dca_pairs: [] },
    })
  })

  it('adds and removes pairs from the full config save payload', () => {
    const store = createConfigStore()

    store.addPair()
    expect(store.state.config.dca_pairs?.[0]).toEqual({
      pair: '',
      amount: 15,
      schedule: {
        enabled: true,
        cron: '0 9 * * *',
        timezone: 'UTC',
      },
      min_order_interval_minutes: 30,
    })
    store.updatePair(0, { pair: 'XETHZEUR' })
    store.removePair(0)

    expect(store.state.config.dca_pairs).toEqual([])
    expect(buildConfigSavePayload(store.state.config)).toEqual({
      config: { dca_pairs: [] },
    })
  })

  it('handles credential replacement and clearing without emitting redacted secrets as new values', () => {
    const store = createConfigStore()
    store.state.config = {
      api: {
        public_key: REDACTED_SECRET,
        private_key: REDACTED_SECRET,
      },
      dca_pairs: [],
    }

    store.replacePublicKey(REDACTED_SECRET)
    expect(store.state.config.api?.public_key).toBe(REDACTED_SECRET)

    store.replacePublicKey('NEW_PUBLIC')
    store.replacePrivateKey('NEW_PRIVATE')
    expect(store.state.config.api).toEqual({
      public_key: 'NEW_PUBLIC',
      private_key: 'NEW_PRIVATE',
    })

    store.clearFilePublicKey()
    store.clearFilePrivateKey()
    expect(store.state.config.api).toEqual({
      public_key: null,
      private_key: null,
    })
  })
})
