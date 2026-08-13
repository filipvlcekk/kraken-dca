<script setup lang="ts">
import type { SchedulerStatus } from '../api'

const props = defineProps<{
  status: SchedulerStatus | null
  onReload: () => void | Promise<void>
}>()

function jobCountLabel(count: number): string {
  return `${count} ${count === 1 ? 'job' : 'jobs'}`
}
</script>

<template>
  <section class="scheduler-status">
    <div class="status-header">
      <div>
        <p class="eyebrow">Scheduler</p>
        <h2>{{ props.status?.running ? 'Scheduler running' : 'Scheduler stopped' }}</h2>
        <p v-if="props.status">{{ jobCountLabel(props.status.jobs.length) }}</p>
        <p v-else>Status not loaded</p>
      </div>
      <button type="button" aria-label="Reload scheduler" @click="props.onReload">
        Reload scheduler
      </button>
    </div>

    <article v-if="props.status && !props.status.config_applied" class="alert">
      <strong>Config mismatch</strong>
      <span>Saved config differs from the active scheduler config.</span>
    </article>

    <article v-if="props.status?.reload_error" class="alert">
      <strong>Reload error</strong>
      <span>{{ props.status.reload_error }}</span>
    </article>

    <ul v-if="props.status" class="jobs">
      <li v-for="job in props.status.jobs" :key="job.id" class="job">
        <div>
          <strong>{{ job.pair }}</strong>
          <span>{{ job.mode }}</span>
        </div>
        <p>{{ job.enabled ? 'Enabled' : 'Disabled' }}</p>
        <p>{{ job.cron ?? 'No cron schedule' }}</p>
        <p>{{ job.timezone }}</p>
        <p>{{ job.next_run_at ?? 'No next run scheduled' }}</p>
        <p v-if="job.running">manual run active</p>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.scheduler-status {
  display: grid;
  gap: var(--space-md);
  padding: var(--space-md);
  border: var(--rule-hairline);
  border-radius: var(--radius-lg);
  background: var(--color-paper-2);
}

.status-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-md);
}

.eyebrow {
  margin: 0 0 var(--space-2xs);
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.status-header h2,
.status-header p,
.job p {
  margin: 0;
}

.status-header h2 {
  font-family: var(--font-display);
  font-size: var(--text-lg);
}

.status-header p,
.job p,
.job span {
  color: var(--color-muted);
}

.alert {
  display: grid;
  gap: var(--space-2xs);
  padding: var(--space-sm);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-sm);
  background: var(--color-warning-soft);
  color: var(--color-ink);
}

.jobs {
  display: grid;
  gap: var(--space-sm);
  margin: 0;
  padding: 0;
  list-style: none;
}

.job {
  display: grid;
  gap: var(--space-xs);
  padding: var(--space-sm);
  border: var(--rule-hairline);
  border-radius: var(--radius-md);
  background: var(--color-paper-3);
}

.job div {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
}

@media (max-width: 48rem) {
  .status-header,
  .job div {
    display: grid;
  }
}
</style>
