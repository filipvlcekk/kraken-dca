<script setup lang="ts">
import type {
  HistoryValuationStatus,
  PortfolioHistorySummary,
} from '../api'

defineProps<{
  portfolio: PortfolioHistorySummary
  valuation: HistoryValuationStatus
}>()

function signed(value: string | null): string {
  if (value === null) {
    return 'No live estimate'
  }
  const numberValue = Number(value)
  if (Number.isNaN(numberValue)) {
    return value
  }
  return numberValue > 0 ? `+${value}` : value
}
</script>

<template>
  <section class="snapshot" aria-label="DCA money snapshot">
    <div class="snapshot-heading">
      <div>
        <p class="eyebrow">Completed bot orders</p>
        <h2>Money snapshot</h2>
      </div>
      <p v-if="valuation.message" class="valuation-note">
        {{ valuation.message }}
      </p>
    </div>

    <dl class="snapshot-grid">
      <div>
        <dt>You spent</dt>
        <dd>{{ portfolio.total_spent }}</dd>
      </div>
      <div>
        <dt>You bought</dt>
        <dd>{{ portfolio.trade_count }} buys</dd>
      </div>
      <div>
        <dt>Worth now</dt>
        <dd>{{ portfolio.estimated_value ?? 'No live estimate' }}</dd>
      </div>
      <div>
        <dt>Estimated gain/loss</dt>
        <dd :class="{ positive: Number(portfolio.estimated_pl) > 0, negative: Number(portfolio.estimated_pl) < 0 }">
          {{ signed(portfolio.estimated_pl) }}
        </dd>
      </div>
    </dl>
  </section>
</template>

<style scoped>
.snapshot {
  display: grid;
  gap: var(--space-md);
  padding: var(--space-md);
  border: var(--rule-hairline);
  border-radius: var(--radius-md);
  background: var(--color-paper-3);
}

.snapshot-heading {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: var(--space-md);
}

.snapshot h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--text-xl);
  letter-spacing: 0;
}

.valuation-note {
  max-width: 24rem;
  margin: 0;
  color: var(--color-warning);
  font-size: var(--text-sm);
  text-align: right;
}

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-sm);
  margin: 0;
}

.snapshot-grid div {
  min-width: 0;
  padding: var(--space-sm);
  border: var(--rule-hairline);
  border-radius: var(--radius-sm);
  background: var(--color-paper-2);
}

dt {
  color: var(--color-muted);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

dd {
  margin: var(--space-2xs) 0 0;
  color: var(--color-ink);
  font-family: var(--font-mono);
  font-size: clamp(var(--text-base), 2vw, var(--text-lg));
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
  .snapshot-heading,
  .snapshot-grid {
    display: grid;
    grid-template-columns: 1fr;
  }

  .valuation-note {
    text-align: left;
  }
}
</style>
