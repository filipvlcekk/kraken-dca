<script setup lang="ts">
import { ref } from 'vue'

import type { HistoryEntry } from '../api'

defineProps<{
  entries: HistoryEntry[]
}>()

const expandedTxid = ref<string | null>(null)

function toggle(txid: string): void {
  expandedTxid.value = expandedTxid.value === txid ? null : txid
}
</script>

<template>
  <section class="history-panel" aria-label="Completed order history">
    <div class="panel-heading">
      <p class="eyebrow">History</p>
      <h2>Completed order history</h2>
    </div>

    <p v-if="entries.length === 0" class="empty-state">
      No completed orders yet.
    </p>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Pair</th>
            <th scope="col">Bought</th>
            <th scope="col">Spent</th>
            <th scope="col">Date</th>
            <th scope="col">Details</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="entry in entries" :key="entry.txid">
            <tr>
              <td>{{ entry.pair }}</td>
              <td>{{ entry.volume }}</td>
              <td>{{ entry.total_price }}</td>
              <td>{{ entry.date }}</td>
              <td>
                <button
                  type="button"
                  class="detail-button"
                  :aria-label="`Show order ${entry.txid} details`"
                  @click="toggle(entry.txid)"
                >
                  Details
                </button>
              </td>
            </tr>
            <tr v-if="expandedTxid === entry.txid" class="detail-row">
              <td colspan="5">
                <dl>
                  <div>
                    <dt>Transaction id</dt>
                    <dd>{{ entry.txid }}</dd>
                  </div>
                  <div>
                    <dt>Exchange fee</dt>
                    <dd>{{ entry.fee }}</dd>
                  </div>
                  <div>
                    <dt>Price before fee</dt>
                    <dd>{{ entry.price }}</dd>
                  </div>
                  <div>
                    <dt>Description</dt>
                    <dd>{{ entry.description }}</dd>
                  </div>
                </dl>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.history-panel {
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

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 760px;
}

th,
td {
  padding: var(--space-xs) var(--space-sm);
  border-bottom: var(--rule-hairline);
  text-align: left;
  vertical-align: top;
}

th {
  color: var(--color-muted);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
}

td {
  color: var(--color-ink-2);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  overflow-wrap: anywhere;
}

.detail-button {
  padding: var(--space-2xs) var(--space-xs);
  font-size: var(--text-sm);
}

.detail-row td {
  background: var(--color-paper-3);
}

dl {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-sm);
  margin: 0;
}

dt {
  color: var(--color-muted);
}

dd {
  margin: var(--space-2xs) 0 0;
}

@media (max-width: 820px) {
  dl {
    grid-template-columns: 1fr;
  }
}
</style>
