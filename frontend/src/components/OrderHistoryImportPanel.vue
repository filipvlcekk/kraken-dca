<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  importHistoryOrders,
  previewHistoryImport,
  type HistoryImportItem,
  type HistoryImportResponse,
} from '../api'

defineProps<{
  csrfToken: string
}>()

const emit = defineEmits<{
  imported: []
}>()

const TXID_PATTERN = /^[A-Z0-9]{6}-[A-Z0-9]{5}-[A-Z0-9]{6}$/

const expanded = ref(false)
const txidInput = ref('')
const preview = ref<HistoryImportResponse | null>(null)
const selectedTxids = ref<string[]>([])
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const previewing = ref(false)
const importing = ref(false)

const parsedTxids = computed(() => {
  const seen = new Set<string>()
  const txids: string[] = []

  for (const value of txidInput.value.split(/[\n,]/)) {
    const txid = value.trim()
    if (!TXID_PATTERN.test(txid) || seen.has(txid)) {
      continue
    }
    seen.add(txid)
    txids.push(txid)
  }

  return txids
})

const previewGroups = computed(() => {
  const groups = new Map<HistoryImportItem['status'], HistoryImportItem[]>()
  for (const item of preview.value?.items ?? []) {
    const group = groups.get(item.status) ?? []
    group.push(item)
    groups.set(item.status, group)
  }
  return Array.from(groups.entries()).map(([status, items]) => ({ status, items }))
})

const previewTxids = computed(() => (preview.value?.items ?? []).map((item) => item.txid))
const readyTxids = computed(() => (preview.value?.items ?? [])
  .filter((item) => item.status === 'ready')
  .map((item) => item.txid))
const selectedReadyTxids = computed(() => selectedTxids.value
  .filter((txid) => readyTxids.value.includes(txid)))

const canPreview = computed(() => parsedTxids.value.length > 0 && !previewing.value)
const canImport = computed(() => selectedReadyTxids.value.length > 0 && !importing.value)

async function previewImport(csrfToken: string): Promise<void> {
  if (!canPreview.value) {
    return
  }

  previewing.value = true
  errorMessage.value = null
  successMessage.value = null
  try {
    const response = await previewHistoryImport(parsedTxids.value, csrfToken)
    if (response.ok) {
      preview.value = response.data
      selectedTxids.value = response.data.items
        .filter((item) => item.status === 'ready')
        .map((item) => item.txid)
    } else {
      errorMessage.value = response.error.message
    }
  } catch {
    errorMessage.value = 'Preview import failed.'
  } finally {
    previewing.value = false
  }
}

async function importSelected(csrfToken: string): Promise<void> {
  if (!canImport.value) {
    return
  }

  importing.value = true
  errorMessage.value = null
  successMessage.value = null
  try {
    const response = await importHistoryOrders(
      previewTxids.value,
      selectedReadyTxids.value,
      csrfToken,
    )
    if (response.ok) {
      preview.value = response.data
      selectedTxids.value = response.data.items
        .filter((item) => item.status === 'ready')
        .map((item) => item.txid)
      successMessage.value = `Imported ${response.data.imported_count} ${response.data.imported_count === 1 ? 'order' : 'orders'}. Skipped ${response.data.skipped_count}.`
      emit('imported')
    } else {
      errorMessage.value = response.error.message
    }
  } catch {
    errorMessage.value = 'Import failed.'
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <section class="import-panel" aria-label="Order history import">
    <button
      type="button"
      class="toggle-button"
      aria-label="Import orders"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      Import orders
    </button>

    <div v-if="expanded" class="import-body">
      <label>
        <span>Order IDs</span>
        <textarea
          v-model="txidInput"
          aria-label="Order transaction ids"
          rows="3"
        />
      </label>

      <div class="actions">
        <button
          type="button"
          aria-label="Preview import"
          :disabled="!canPreview"
          @click="previewImport(csrfToken)"
        >
          {{ previewing ? 'Previewing...' : 'Preview import' }}
        </button>
        <button
          type="button"
          aria-label="Import selected"
          :disabled="!canImport"
          @click="importSelected(csrfToken)"
        >
          {{ importing ? 'Importing...' : 'Import selected' }}
        </button>
      </div>

      <p
        v-if="errorMessage || successMessage"
        class="status-line"
        :class="{ error: errorMessage, success: successMessage }"
      >
        {{ errorMessage || successMessage }}
      </p>

      <div v-if="previewGroups.length > 0" class="preview-groups">
        <section
          v-for="group in previewGroups"
          :key="group.status"
          class="preview-group"
        >
          <h3>{{ group.status }} ({{ group.items.length }})</h3>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Import</th>
                  <th scope="col">Txid</th>
                  <th scope="col">Message</th>
                  <th scope="col">Target</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in group.items" :key="item.txid">
                  <td>
                    <input
                      v-if="item.status === 'ready'"
                      v-model="selectedTxids"
                      type="checkbox"
                      :value="item.txid"
                      :aria-label="`Select ${item.txid}`"
                    >
                  </td>
                  <td>{{ item.txid }}</td>
                  <td>{{ item.message || item.status }}</td>
                  <td>{{ item.target_file || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped>
.import-panel {
  display: grid;
  gap: var(--space-sm);
  padding: var(--space-md);
  border: var(--rule-hairline);
  border-radius: var(--radius-md);
  background: var(--color-paper-2);
}

.toggle-button {
  justify-self: start;
}

.import-body {
  display: grid;
  gap: var(--space-sm);
}

label {
  display: grid;
  gap: var(--space-2xs);
  color: var(--color-muted);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
}

textarea {
  width: 100%;
  min-width: 0;
  border: var(--rule-strong);
  border-radius: var(--radius-sm);
  padding: var(--space-sm);
  background: var(--color-field);
  color: var(--color-ink);
  font: inherit;
  resize: vertical;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

.status-line {
  margin: 0;
  font-size: var(--text-sm);
}

.status-line.error {
  color: var(--color-danger);
}

.status-line.success {
  color: var(--color-success);
}

.preview-groups {
  display: grid;
  gap: var(--space-sm);
}

.preview-group {
  display: grid;
  gap: var(--space-xs);
}

h3 {
  margin: 0;
  color: var(--color-ink);
  font-family: var(--font-display);
  font-size: var(--text-md);
  letter-spacing: 0;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 680px;
  border-collapse: collapse;
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

input[type='checkbox'] {
  width: 1rem;
  min-height: 1rem;
  accent-color: var(--color-accent);
}
</style>
