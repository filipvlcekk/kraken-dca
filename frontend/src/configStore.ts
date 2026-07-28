import { reactive } from 'vue'

import {
  REDACTED_SECRET,
  loadConfig,
  saveConfig,
  type ApiResponse,
  type AppConfig,
  type ConfigResponse,
  type DcaPairConfig,
  type SaveConfigResponse,
  type SecretMetadata,
} from './api'

type SecretState = {
  public_key: SecretMetadata
  private_key: SecretMetadata
}

export type ConfigStoreState = {
  config: AppConfig
  secrets: SecretState
  configValid: boolean
  validationErrors: Record<string, string>
  dirty: boolean
  loading: boolean
  saving: boolean
  setupMode: boolean
  configPersistenceError: string | null
  orderHistoryWarning: string | null
}

type ConfigStoreApi = {
  loadConfig: () => Promise<ApiResponse<ConfigResponse>>
  saveConfig: (
    config: AppConfig,
    csrfToken: string,
  ) => Promise<ApiResponse<SaveConfigResponse>>
}

const DEFAULT_PAIR: DcaPairConfig = {
  pair: '',
  amount: 15,
  schedule: {
    enabled: true,
    cron: '0 9 * * *',
    timezone: 'UTC',
  },
  min_order_interval_minutes: 30,
}

const EMPTY_SECRETS: SecretState = {
  public_key: { configured: false, source: null },
  private_key: { configured: false, source: null },
}

export function createConfigStore(api: Partial<ConfigStoreApi> = {}) {
  const client: ConfigStoreApi = {
    loadConfig: api.loadConfig ?? loadConfig,
    saveConfig: api.saveConfig ?? saveConfig,
  }
  const state = reactive<ConfigStoreState>({
    config: { dca_pairs: [] },
    secrets: { ...EMPTY_SECRETS },
    configValid: false,
    validationErrors: {},
    dirty: false,
    loading: false,
    saving: false,
    setupMode: false,
    configPersistenceError: null,
    orderHistoryWarning: null,
  })

  async function load(): Promise<boolean> {
    state.loading = true
    try {
      const response = await client.loadConfig()
      if (!response.ok) {
        state.validationErrors = response.error.fields ?? {
          config: response.error.message,
        }
        return false
      }
      applyConfigResponse(response.data)
      state.dirty = false
      return true
    } finally {
      state.loading = false
    }
  }

  async function save(csrfToken: string): Promise<boolean> {
    state.saving = true
    state.configPersistenceError = null
    try {
      const payload = buildConfigSavePayload(state.config)
      const response = await client.saveConfig(payload.config, csrfToken)
      if (!response.ok) {
        state.validationErrors = response.error.fields ?? {}
        if (response.error.code === 'config_persistence_failed') {
          state.configPersistenceError = response.error.message
        }
        return false
      }
      applyConfigResponse(response.data)
      state.dirty = false
      return true
    } finally {
      state.saving = false
    }
  }

  function updatePair(index: number, patch: Partial<DcaPairConfig>): void {
    const pairs = ensurePairs()
    const current = pairs[index]
    if (current === undefined) {
      return
    }
    pairs[index] = { ...current, ...patch }
    markDirty()
  }

  function addPair(): void {
    ensurePairs().push(structuredClone(DEFAULT_PAIR))
    markDirty()
  }

  function removePair(index: number): void {
    ensurePairs().splice(index, 1)
    markDirty()
  }

  function replacePublicKey(value: string): void {
    replaceCredential('public_key', value)
  }

  function replacePrivateKey(value: string): void {
    replaceCredential('private_key', value)
  }

  function clearFilePublicKey(): void {
    clearCredential('public_key')
  }

  function clearFilePrivateKey(): void {
    clearCredential('private_key')
  }

  function ensurePairs(): DcaPairConfig[] {
    if (state.config.dca_pairs === undefined) {
      state.config.dca_pairs = []
    }
    return state.config.dca_pairs
  }

  function replaceCredential(key: 'public_key' | 'private_key', value: string): void {
    if (!value || value === REDACTED_SECRET) {
      return
    }
    ensureApi()[key] = value
    markDirty()
  }

  function clearCredential(key: 'public_key' | 'private_key'): void {
    ensureApi()[key] = null
    markDirty()
  }

  function ensureApi(): NonNullable<AppConfig['api']> {
    if (state.config.api === undefined) {
      state.config.api = {}
    }
    return state.config.api
  }

  function markDirty(): void {
    state.dirty = true
  }

  function applyConfigResponse(data: ConfigResponse): void {
    state.config = normalizeConfig(data.config)
    state.secrets = data.secrets
    state.configValid = data.config_valid
    state.validationErrors = data.validation_errors
    state.setupMode = data.validation_errors.config === 'Config file not found.'
  }

  return {
    state,
    load,
    save,
    updatePair,
    addPair,
    removePair,
    replacePublicKey,
    replacePrivateKey,
    clearFilePublicKey,
    clearFilePrivateKey,
  }
}

export function buildConfigSavePayload(config: AppConfig): { config: AppConfig } {
  return { config: normalizeConfig(config) }
}

function normalizeConfig(config: AppConfig): AppConfig {
  return {
    ...config,
    dca_pairs: (config.dca_pairs ?? []).map((pair) => {
      if (pair.schedule === undefined) {
        return { ...pair }
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
