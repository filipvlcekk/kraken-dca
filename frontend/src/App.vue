<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { createAuthStore } from './authStore'
import type { DcaPairConfig } from './api'
import ConfigWarnings from './components/ConfigWarnings.vue'
import CredentialEditor from './components/CredentialEditor.vue'
import LoginView from './components/LoginView.vue'
import PairEditor from './components/PairEditor.vue'
import SchedulerStatus from './components/SchedulerStatus.vue'
import { createConfigStore } from './configStore'
import { createSchedulerStore } from './schedulerStore'

const auth = createAuthStore()
const config = createConfigStore()
const scheduler = createSchedulerStore()
const pairs = computed(() => config.state.config.dca_pairs ?? [])

onMounted(async () => {
  const restored = await auth.restore()
  if (restored) {
    await loadDashboard()
  }
})

async function loadDashboard(): Promise<void> {
  await Promise.all([
    config.load(),
    scheduler.loadStatus(),
  ])
}

async function handleLogin(password: string): Promise<void> {
  const loggedIn = await auth.login(password)
  if (loggedIn) {
    await loadDashboard()
  }
}

async function handleLogout(): Promise<void> {
  await auth.logout()
}

async function saveConfig(): Promise<void> {
  if (auth.state.csrfToken === null) {
    return
  }
  const saved = await config.save(auth.state.csrfToken)
  if (saved) {
    await scheduler.reload(auth.state.csrfToken)
  }
}

async function reloadScheduler(): Promise<void> {
  if (auth.state.csrfToken !== null) {
    await scheduler.reload(auth.state.csrfToken)
  }
}

async function runPairNow(pair: string): Promise<void> {
  if (auth.state.csrfToken !== null && pair) {
    await scheduler.runPairNow(pair, auth.state.csrfToken)
  }
}

function updatePair(index: number, pairConfig: DcaPairConfig): void {
  config.updatePair(index, pairConfig)
}

function pairFieldErrors(index: number): Record<string, string> {
  const prefix = `dca_pairs.${index}.`
  return Object.fromEntries(
    Object.entries(config.state.validationErrors)
      .filter(([field]) => field.startsWith(prefix))
      .map(([field, message]) => [field.slice(prefix.length), message]),
  )
}
</script>

<template>
  <main class="app-shell">
    <p v-if="auth.state.restoring" class="loading">Checking session...</p>

    <LoginView
      v-else-if="!auth.state.authenticated"
      :loading="auth.state.loginPending"
      :error="auth.state.error"
      @login="handleLogin"
    />

    <section v-else class="dashboard">
      <header class="hero">
        <div>
          <p class="eyebrow">Authenticated dashboard</p>
          <h1>Kraken DCA scheduler</h1>
          <p>
            Edit writable config, preview cron schedules, reload the in-container
            scheduler, and trigger controlled manual runs.
          </p>
        </div>
        <button type="button" :disabled="auth.state.logoutPending" @click="handleLogout">
          Logout
        </button>
      </header>

      <ConfigWarnings
        :config-valid="config.state.configValid"
        :validation-errors="config.state.validationErrors"
        :config-persistence-error="config.state.configPersistenceError"
        :order-history-warning="config.state.orderHistoryWarning"
        :setup-mode="config.state.setupMode"
      />

      <div class="dashboard-grid">
        <section class="panel credentials-panel">
          <div class="panel-heading">
            <p class="eyebrow">Secrets</p>
            <h2>Kraken credentials</h2>
          </div>
          <CredentialEditor
            :api-config="config.state.config.api"
            :secrets="config.state.secrets"
            @replace-public-key="config.replacePublicKey"
            @replace-private-key="config.replacePrivateKey"
            @clear-file-public-key="config.clearFilePublicKey"
            @clear-file-private-key="config.clearFilePrivateKey"
          />
        </section>

        <SchedulerStatus
          :status="scheduler.state.status"
          :on-reload="reloadScheduler"
        />
      </div>

      <section class="pairs-section">
        <div class="panel-heading row">
          <div>
            <p class="eyebrow">Trading plan</p>
            <h2>DCA pairs</h2>
          </div>
          <button type="button" @click="config.addPair">Add pair</button>
        </div>

        <div class="pairs-grid">
          <PairEditor
            v-for="(pair, index) in pairs"
            :key="index"
            :pair-config="pair"
            :field-errors="pairFieldErrors(index)"
            :manual-run-state="scheduler.state.manualRuns[pair.pair] ?? null"
            @update:pair-config="updatePair(index, $event)"
            @run-now="runPairNow(pair.pair)"
            @remove="config.removePair(index)"
          />
        </div>
      </section>

      <footer class="save-bar">
        <div>
          <strong>{{ config.state.dirty ? 'Unsaved changes' : 'Config synchronized' }}</strong>
          <p>Saving writes the full config.yaml and reloads scheduler jobs.</p>
        </div>
        <button type="button" :disabled="config.state.saving" @click="saveConfig">
          Save config
        </button>
      </footer>
    </section>
  </main>
</template>

<style scoped>
.app-shell {
  width: min(100%, 1180px);
}

.loading {
  padding: 1rem 1.2rem;
  border-radius: 999px;
  background: rgba(255, 252, 241, 0.88);
  box-shadow: 0 18px 60px rgba(37, 43, 28, 0.14);
}

.dashboard {
  display: grid;
  gap: clamp(1rem, 2vw, 1.5rem);
}

.hero,
.panel,
.pairs-section,
.save-bar {
  border: 1px solid rgba(42, 50, 32, 0.14);
  box-shadow: 0 26px 80px rgba(37, 43, 28, 0.12);
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: clamp(1.3rem, 4vw, 2.4rem);
  border-radius: 34px;
  background:
    radial-gradient(circle at 82% 8%, rgba(226, 167, 68, 0.32), transparent 32%),
    linear-gradient(140deg, rgba(255, 252, 241, 0.96), rgba(229, 219, 193, 0.84));
}

.hero h1 {
  max-width: 11ch;
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(3rem, 8vw, 6.6rem);
  line-height: 0.86;
  letter-spacing: -0.08em;
}

.hero p:not(.eyebrow) {
  max-width: 42rem;
  margin: 1rem 0 0;
  color: var(--color-muted);
  font-size: 1.08rem;
}

.eyebrow {
  margin: 0 0 0.35rem;
  color: var(--color-rust);
  font-size: 0.75rem;
  font-weight: 900;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: 1rem;
}

.panel,
.pairs-section {
  padding: 1rem;
  border-radius: 28px;
  background: rgba(255, 252, 241, 0.78);
}

.panel-heading h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.8rem, 3vw, 3rem);
  letter-spacing: -0.05em;
}

.row,
.save-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.pairs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.save-bar {
  position: sticky;
  bottom: 1rem;
  padding: 1rem;
  border-radius: 24px;
  background: rgba(35, 49, 31, 0.94);
  color: #f8ead0;
}

.save-bar p {
  margin: 0.25rem 0 0;
  color: rgba(248, 234, 208, 0.76);
}

@media (max-width: 820px) {
  .hero,
  .dashboard-grid,
  .row,
  .save-bar {
    display: grid;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}
</style>
