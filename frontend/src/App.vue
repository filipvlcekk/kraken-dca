<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { createAuthStore } from './authStore'
import type { DcaPairConfig } from './api'
import ConfigWarnings from './components/ConfigWarnings.vue'
import CredentialEditor from './components/CredentialEditor.vue'
import LoginView from './components/LoginView.vue'
import OrderHistoryTable from './components/OrderHistoryTable.vue'
import PairEditor from './components/PairEditor.vue'
import PairStatusPanel from './components/PairStatusPanel.vue'
import PortfolioSnapshot from './components/PortfolioSnapshot.vue'
import ProfitLossChart from './components/ProfitLossChart.vue'
import SchedulerStatus from './components/SchedulerStatus.vue'
import { createConfigStore } from './configStore'
import { createHistoryStore } from './historyStore'
import { createSchedulerStore } from './schedulerStore'

const auth = createAuthStore()
const config = createConfigStore()
const scheduler = createSchedulerStore()
const history = createHistoryStore()
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
    history.load(),
  ])
}

async function handleLogin(password: string): Promise<void> {
  const loggedIn = await auth.login(password)
  if (loggedIn) {
    await loadDashboard()
  }
}

function handleOidcLogin(url: string): void {
  window.location.href = url
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
    await history.load()
  }
}

async function reloadScheduler(): Promise<void> {
  if (auth.state.csrfToken !== null) {
    await scheduler.reload(auth.state.csrfToken)
    await history.load()
  }
}

async function runPairNow(pair: string): Promise<void> {
  if (auth.state.csrfToken !== null && pair) {
    const ran = await scheduler.runPairNow(pair, auth.state.csrfToken)
    if (ran) {
      await history.load()
    }
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
      :auth-mode="auth.state.authMode"
      :oidc-login-url="auth.state.oidcLoginUrl"
      @login="handleLogin"
      @oidc-login="handleOidcLogin"
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

      <div v-if="history.state.history" class="history-overview">
        <PortfolioSnapshot
          :portfolio="history.state.history.portfolio"
          :valuation="history.state.history.valuation"
        />
        <PairStatusPanel
          :pairs="history.state.history.pairs"
          :jobs="scheduler.state.status?.jobs ?? []"
        />
        <ProfitLossChart
          :points="history.state.history.chart"
          :estimated-value="history.state.history.portfolio.estimated_value"
        />
      </div>

      <p v-else-if="history.state.loading" class="loading">
        Loading completed orders...
      </p>
      <p v-else-if="history.state.error" class="history-error">
        {{ history.state.error }}
      </p>

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

      <OrderHistoryTable
        v-if="history.state.history"
        :entries="history.state.history.entries"
      />

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
  margin-inline: auto;
}

.loading {
  width: fit-content;
  padding: var(--space-sm) var(--space-md);
  border: var(--rule-hairline);
  border-radius: var(--radius-sm);
  background: var(--color-paper-2);
  color: var(--color-ink-2);
  font-family: var(--font-mono);
}

.dashboard {
  display: grid;
  gap: clamp(var(--space-md), 2vw, var(--space-lg));
}

.hero,
.save-bar {
  border: var(--rule-hairline);
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: var(--space-lg);
  padding: clamp(var(--space-lg), 4vw, var(--space-xl));
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--color-paper-3), var(--color-paper-2));
}

.hero h1 {
  max-width: 18ch;
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--text-display);
  line-height: 1.05;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}

.hero p:not(.eyebrow) {
  max-width: 42rem;
  margin: var(--space-sm) 0 0;
  color: var(--color-ink-2);
  font-size: var(--text-base);
}

.eyebrow {
  margin: 0 0 var(--space-xs);
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: var(--space-md);
}

.history-overview {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: var(--space-md);
}

.history-overview > :first-child {
  grid-column: 1 / -1;
}

.history-error {
  margin: 0;
  padding: var(--space-sm) var(--space-md);
  border: var(--rule-hairline);
  border-radius: var(--radius-sm);
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.panel,
.pairs-section {
  min-width: 0;
}

.panel-heading h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(var(--text-lg), 2vw, var(--text-xl));
  line-height: 1.15;
  letter-spacing: 0;
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
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  gap: var(--space-md);
  margin-top: var(--space-md);
}

.save-bar {
  z-index: var(--z-sticky);
  position: sticky;
  bottom: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-md);
  background: var(--color-paper-4);
  color: var(--color-ink);
}

.save-bar p {
  margin: var(--space-2xs) 0 0;
  color: var(--color-muted);
}

@media (max-width: 820px) {
  .hero,
  .dashboard-grid,
  .history-overview,
  .row,
  .save-bar {
    display: grid;
  }

  .dashboard-grid,
  .history-overview {
    grid-template-columns: 1fr;
  }

  .hero {
    grid-template-columns: 1fr;
  }
}
</style>
