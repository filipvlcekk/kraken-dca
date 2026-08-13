<script setup lang="ts">
import type { PairHistorySummary, SchedulerJob } from '../api'

const props = defineProps<{
  pairs: PairHistorySummary[]
  jobs: SchedulerJob[]
}>()

function jobFor(pair: string): SchedulerJob | undefined {
  return props.jobs.find((job) => job.pair === pair)
}

function statusLabel(pair: string): string {
  const job = jobFor(pair)
  if (job?.running) {
    return 'Running now'
  }
  if (job?.enabled) {
    return 'Active'
  }
  if (job) {
    return 'Paused'
  }
  return 'No schedule'
}

function signed(value: string | null): string {
  if (value === null) {
    return 'No live estimate'
  }
  return Number(value) > 0 ? `+${value}` : value
}
</script>

<template>
  <section class="pair-status" aria-label="DCA pair status">
    <div class="panel-heading">
      <p class="eyebrow">Pair status</p>
      <h2>DCA pairs at a glance</h2>
    </div>

    <p v-if="pairs.length === 0" class="empty-state">
      No completed orders yet. Pair status will fill in after the bot records buys.
    </p>

    <div v-else class="pair-list">
      <article v-for="pair in pairs" :key="pair.pair" class="pair-row">
        <div class="pair-main">
          <strong>{{ pair.pair }}</strong>
          <span>{{ statusLabel(pair.pair) }}</span>
        </div>
        <dl>
          <div>
            <dt>Buys completed</dt>
            <dd>{{ pair.trade_count }}</dd>
          </div>
          <div>
            <dt>Total spent</dt>
            <dd>{{ pair.total_spent }}</dd>
          </div>
          <div>
            <dt>Average buy price</dt>
            <dd>{{ pair.average_buy_price ?? 'Not enough data' }}</dd>
          </div>
          <div>
            <dt>Estimated gain/loss</dt>
            <dd :class="{ positive: Number(pair.estimated_pl) > 0, negative: Number(pair.estimated_pl) < 0 }">
              {{ signed(pair.estimated_pl) }}
            </dd>
          </div>
        </dl>
      </article>
    </div>
  </section>
</template>

<style scoped>
.pair-status {
  display: grid;
  gap: var(--space-md);
  padding: var(--space-md);
  border: var(--rule-hairline);
  border-radius: var(--radius-md);
  background: var(--color-paper-2);
}

.panel-heading h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--text-xl);
  letter-spacing: 0;
}

.empty-state {
  margin: 0;
  color: var(--color-muted);
}

.pair-list {
  display: grid;
  gap: var(--space-sm);
}

.pair-row {
  display: grid;
  gap: var(--space-sm);
  padding: var(--space-sm);
  border: var(--rule-hairline);
  border-radius: var(--radius-sm);
  background: var(--color-paper-3);
}

.pair-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}

.pair-main strong {
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}

.pair-main span {
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

dl {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-sm);
  margin: 0;
}

dt {
  color: var(--color-muted);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

dd {
  margin: var(--space-2xs) 0 0;
  font-family: var(--font-mono);
  font-weight: 800;
  overflow-wrap: anywhere;
}

.positive {
  color: var(--color-success);
}

.negative {
  color: var(--color-danger);
}

@media (max-width: 820px) {
  .pair-main,
  dl {
    display: grid;
    grid-template-columns: 1fr;
  }
}
</style>
