<script setup lang="ts">
import { ref } from 'vue'

import { REDACTED_SECRET, type SecretMetadata } from '../api'

type ApiConfig = {
  public_key?: string | null
  private_key?: string | null
}

const props = defineProps<{
  apiConfig?: ApiConfig
  secrets: {
    public_key: SecretMetadata
    private_key: SecretMetadata
  }
}>()

const emit = defineEmits<{
  'replace-public-key': [value: string]
  'replace-private-key': [value: string]
  'clear-file-public-key': []
  'clear-file-private-key': []
}>()

const replacingPublic = ref(false)
const replacingPrivate = ref(false)
const publicReplacement = ref('')
const privateReplacement = ref('')

function credentialStatus(secret: SecretMetadata): string {
  if (secret.source === 'file') {
    return 'Configured in config.yaml'
  }
  if (secret.source === 'env') {
    return 'Environment variable configured'
  }
  return 'Not configured'
}

function credentialDisplay(value: string | null | undefined, secret: SecretMetadata): string {
  if (secret.source === 'file' && value === REDACTED_SECRET) {
    return 'Redacted'
  }
  if (!value) {
    return 'Omitted from config.yaml'
  }
  return 'Replacement ready'
}

function savePublicReplacement(): void {
  const value = publicReplacement.value.trim()
  if (!value || value === REDACTED_SECRET) {
    return
  }
  emit('replace-public-key', value)
  publicReplacement.value = ''
  replacingPublic.value = false
}

function savePrivateReplacement(): void {
  const value = privateReplacement.value.trim()
  if (!value || value === REDACTED_SECRET) {
    return
  }
  emit('replace-private-key', value)
  privateReplacement.value = ''
  replacingPrivate.value = false
}
</script>

<template>
  <section class="credentials">
    <article class="credential">
      <div>
        <h2>Public API key</h2>
        <p>{{ credentialStatus(props.secrets.public_key) }}</p>
        <p>{{ credentialDisplay(props.apiConfig?.public_key, props.secrets.public_key) }}</p>
      </div>
      <button
        type="button"
        aria-label="Replace public API key"
        @click="replacingPublic = true"
      >
        Replace
      </button>
      <button
        v-if="props.secrets.public_key.source === 'file'"
        type="button"
        aria-label="Clear public API key"
        @click="emit('clear-file-public-key')"
      >
        Clear file credential
      </button>
      <div v-if="replacingPublic" class="replacement">
        <input
          v-model="publicReplacement"
          aria-label="New public API key"
          autocomplete="off"
        />
        <button
          type="button"
          aria-label="Save public API key"
          @click="savePublicReplacement"
        >
          Save public key
        </button>
      </div>
    </article>

    <article class="credential">
      <div>
        <h2>Private API key</h2>
        <p>{{ credentialStatus(props.secrets.private_key) }}</p>
        <p>{{ credentialDisplay(props.apiConfig?.private_key, props.secrets.private_key) }}</p>
      </div>
      <button
        type="button"
        aria-label="Replace private API key"
        @click="replacingPrivate = true"
      >
        Replace
      </button>
      <button
        v-if="props.secrets.private_key.source === 'file'"
        type="button"
        aria-label="Clear private API key"
        @click="emit('clear-file-private-key')"
      >
        Clear file credential
      </button>
      <div v-if="replacingPrivate" class="replacement">
        <input
          v-model="privateReplacement"
          aria-label="New private API key"
          autocomplete="off"
        />
        <button
          type="button"
          aria-label="Save private API key"
          @click="savePrivateReplacement"
        >
          Save private key
        </button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.credentials {
  display: grid;
  gap: 1rem;
}

.credential {
  display: grid;
  gap: 0.75rem;
  padding: 1rem;
  border: 1px solid rgba(42, 50, 32, 0.16);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.5);
}

.credential h2,
.credential p {
  margin: 0;
}

.replacement {
  display: flex;
  gap: 0.5rem;
}
</style>
