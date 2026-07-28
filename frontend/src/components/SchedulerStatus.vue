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
  gap: 1rem;
  padding: 1rem;
  border: 1px solid rgba(44, 58, 40, 0.14);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, rgba(236, 190, 91, 0.18), transparent 32%),
    rgba(250, 247, 237, 0.82);
}

.status-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.eyebrow {
  margin: 0 0 0.25rem;
  color: #69705a;
  font-size: 0.78rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.status-header h2,
.status-header p,
.job p {
  margin: 0;
}

.alert {
  display: grid;
  gap: 0.25rem;
  padding: 0.75rem;
  border-radius: 16px;
  background: rgba(199, 92, 42, 0.12);
  color: #5b311d;
}

.jobs {
  display: grid;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.job {
  display: grid;
  gap: 0.35rem;
  padding: 0.85rem;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.58);
}

.job div {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
</style>
