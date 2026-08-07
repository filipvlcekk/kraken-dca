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
  padding: clamp(1.5rem, 4vw, 3rem);
  border: 1px solid rgba(42, 50, 32, 0.14);
  border-radius: 34px;
  background:
    radial-gradient(circle at 100% 0%, rgba(226, 167, 68, 0.28), transparent 34%),
    linear-gradient(145deg, rgba(255, 252, 241, 0.94), rgba(236, 226, 201, 0.86));
  box-shadow: 0 34px 100px rgba(37, 43, 28, 0.18);
}

.mark {
  display: inline-grid;
  width: 4rem;
  height: 4rem;
  place-items: center;
  border-radius: 1.4rem;
  background: #23311f;
  color: #f8ead0;
  font-weight: 900;
  letter-spacing: -0.05em;
}

.eyebrow {
  margin: 1.4rem 0 0.5rem;
  color: var(--color-rust);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h1 {
  max-width: 10ch;
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(3rem, 11vw, 6.8rem);
  line-height: 0.85;
  letter-spacing: -0.08em;
}

.lede {
  max-width: 34rem;
  margin: 1.25rem 0 0;
  color: var(--color-muted);
  font-size: 1.05rem;
}

.login-form {
  display: grid;
  gap: 0.9rem;
  margin-top: 2rem;
}

label {
  display: grid;
  gap: 0.4rem;
  font-weight: 800;
}

.error {
  margin: 1rem 0 0;
  color: var(--color-danger);
  font-weight: 800;
}
</style>
