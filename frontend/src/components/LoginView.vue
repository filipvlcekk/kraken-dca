<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  loading: boolean
  error: string | null
  authMode: 'password' | 'oidc' | null
  oidcLoginUrl: string | null
}>()

const emit = defineEmits<{
  login: [password: string]
  'oidc-login': [url: string]
}>()

const password = ref('')

function submit(): void {
  emit('login', password.value)
}

function startOidcLogin(url: string | null): void {
  if (url !== null) {
    emit('oidc-login', url)
  }
}
</script>

<template>
  <section class="login-view">
    <div class="mark">DCA</div>
    <p class="eyebrow">Docker Web UI</p>
    <h1>Sign in to Kraken DCA</h1>
    <p class="lede">
      Configure writable <code>config.yaml</code>, per-pair cron schedules, and
      manual execution from the same container runtime.
    </p>

    <div v-if="authMode === 'oidc'" class="login-form">
      <button
        type="button"
        :disabled="loading || oidcLoginUrl === null"
        @click="startOidcLogin(oidcLoginUrl)"
      >
        Sign in with Pocket ID
      </button>
    </div>

    <form v-else class="login-form" @submit.prevent="submit">
      <label>
        Web UI password
        <input
          v-model="password"
          aria-label="Web UI password"
          type="password"
          autocomplete="current-password"
        />
      </label>
      <button type="submit" :disabled="loading">
        {{ loading ? 'Signing in...' : 'Sign in' }}
      </button>
    </form>

    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>

<style scoped>
.login-view {
  width: min(100%, 620px);
  margin-inline: auto;
  padding: clamp(var(--space-lg), 4vw, var(--space-xl));
  border: var(--rule-hairline);
  border-radius: var(--radius-lg);
  background: linear-gradient(145deg, var(--color-paper-3), var(--color-paper-2));
}

.mark {
  display: inline-grid;
  width: 3.5rem;
  height: 3.5rem;
  place-items: center;
  border: var(--rule-strong);
  border-radius: var(--radius-md);
  background: var(--color-paper);
  color: var(--color-accent);
  font-family: var(--font-display);
  font-weight: 800;
  letter-spacing: 0;
}

.eyebrow {
  margin: var(--space-lg) 0 var(--space-xs);
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1 {
  max-width: 16ch;
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--text-display);
  line-height: 1.05;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}

.lede {
  max-width: 34rem;
  margin: var(--space-md) 0 0;
  color: var(--color-ink-2);
  font-size: var(--text-base);
}

.login-form {
  display: grid;
  gap: var(--space-sm);
  margin-top: var(--space-xl);
}

label {
  display: grid;
  gap: var(--space-xs);
  color: var(--color-ink-2);
  font-weight: 800;
}

.error {
  margin: var(--space-md) 0 0;
  padding: var(--space-sm);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  background: var(--color-danger-soft);
  color: var(--color-danger);
  font-weight: 800;
}
</style>
