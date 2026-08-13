<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  searchAssetPairs,
  type AssetPairSuggestion,
  type DcaPairConfig,
  type DcaPairSchedule,
} from '../api'
import type { ManualRunState } from '../schedulerStore'
import ScheduleEditor from './ScheduleEditor.vue'

const props = defineProps<{
  pairConfig: DcaPairConfig
  fieldErrors: Record<string, string>
  manualRunState: ManualRunState | null
}>()

const emit = defineEmits<{
  'update:pairConfig': [pairConfig: DcaPairConfig]
  'run-now': []
  remove: []
}>()

const pairLabel = computed(() => props.pairConfig.pair || 'pair')
const pairInput = ref(props.pairConfig.pair)
const pairSuggestions = ref<AssetPairSuggestion[]>([])
const pairSuggestionsOpen = ref(false)
const pairSuggestionsLoading = ref(false)
const pairSuggestionError = ref<string | null>(null)
let latestPairSearchId = 0
const scheduleFieldErrors = computed(() => {
  const entries = Object.entries(props.fieldErrors)
    .filter(([field]) => field.startsWith('schedule.'))
    .map(([field, message]) => [field.replace(/^schedule\./, ''), message])
  return Object.fromEntries(entries)
})

function updatePair(patch: Partial<DcaPairConfig>): void {
  emit('update:pairConfig', {
    ...props.pairConfig,
    ...patch,
  })
}

watch(
  () => props.pairConfig.pair,
  (pair) => {
    if (pair !== pairInput.value) {
      pairInput.value = pair
    }
  },
)

async function updatePairInput(event: Event): Promise<void> {
  const value = (event.target as HTMLInputElement).value
  pairInput.value = value
  updatePair({ pair: value })
  await fetchPairSuggestions(value)
}

async function fetchPairSuggestions(value: string): Promise<void> {
  const query = value.trim()
  latestPairSearchId += 1
  const searchId = latestPairSearchId

  if (query === '') {
    pairSuggestions.value = []
    pairSuggestionsOpen.value = false
    pairSuggestionsLoading.value = false
    pairSuggestionError.value = null
    return
  }

  pairSuggestionsOpen.value = true
  pairSuggestionsLoading.value = true
  pairSuggestionError.value = null
  pairSuggestions.value = []

  let response: Awaited<ReturnType<typeof searchAssetPairs>>
  try {
    response = await searchAssetPairs(query)
  } catch {
    if (searchId !== latestPairSearchId) {
      return
    }
    pairSuggestionsLoading.value = false
    pairSuggestions.value = []
    pairSuggestionError.value = 'Pair search failed.'
    pairSuggestionsOpen.value = true
    return
  }

  if (searchId !== latestPairSearchId) {
    return
  }

  pairSuggestionsLoading.value = false
  if (response.ok) {
    pairSuggestions.value = response.data
    pairSuggestionsOpen.value = response.data.length > 0
  } else {
    pairSuggestions.value = []
    pairSuggestionError.value = response.error.message
    pairSuggestionsOpen.value = true
  }
}

function selectPairSuggestion(suggestion: AssetPairSuggestion): void {
  pairInput.value = suggestion.pair
  pairSuggestions.value = []
  pairSuggestionsOpen.value = false
  updatePair({ pair: suggestion.pair })
}

function suggestionLabel(suggestion: AssetPairSuggestion): string {
  return suggestion.wsname || suggestion.altname || suggestion.pair
}

function suggestionMeta(suggestion: AssetPairSuggestion): string {
  const label = suggestionLabel(suggestion)
  const labels = [suggestion.altname, suggestion.pair].filter(
    (item) => item && item !== label,
  )
  return labels.join(' | ')
}

function updateNumber(
  field: 'amount' | 'limit_factor' | 'max_price',
  event: Event,
): void {
  const value = (event.target as HTMLInputElement).value
  updatePair({ [field]: value === '' ? undefined : Number(value) })
}

function updateBoolean(field: 'ignore_differing_orders', event: Event): void {
  updatePair({ [field]: (event.target as HTMLInputElement).checked })
}

function updateSchedule(schedule: DcaPairSchedule): void {
  updatePair({ schedule })
}

function updateMinInterval(value: number): void {
  updatePair({ min_order_interval_minutes: value })
}
</script>

<template>
  <article class="pair-editor">
    <header>
      <div>
        <p class="eyebrow">DCA pair</p>
        <h2>{{ pairLabel }}</h2>
      </div>
      <div class="actions">
        <button type="button" :aria-label="`Run ${pairLabel} now`" @click="emit('run-now')">
          Run now
        </button>
        <button type="button" :aria-label="`Remove ${pairLabel}`" @click="emit('remove')">
          Remove
        </button>
      </div>
    </header>

    <div class="fields">
      <label class="pair-combobox">
        Pair name
        <div
          class="pair-combobox-control"
          role="combobox"
          :aria-expanded="pairSuggestionsOpen"
          aria-haspopup="listbox"
        >
          <input
            :value="pairInput"
            aria-label="Pair name"
            aria-autocomplete="list"
            autocomplete="off"
            @focus="pairSuggestionsOpen = pairSuggestions.length > 0"
            @input="updatePairInput"
          />
          <ul
            v-if="pairSuggestionsOpen"
            class="pair-suggestions"
            role="listbox"
            aria-label="Pair suggestions"
          >
            <li v-if="pairSuggestionsLoading" class="pair-suggestion-status">
              Loading pairs...
            </li>
            <li v-else-if="pairSuggestionError" class="pair-suggestion-status">
              {{ pairSuggestionError }}
            </li>
            <li v-for="suggestion in pairSuggestions" :key="suggestion.pair">
              <button
                type="button"
                role="option"
                :aria-label="`Select ${suggestionLabel(suggestion)}`"
                @mousedown.prevent
                @click="selectPairSuggestion(suggestion)"
              >
                <span>{{ suggestionLabel(suggestion) }}</span>
                <small v-if="suggestionMeta(suggestion)">
                  {{ suggestionMeta(suggestion) }}
                </small>
              </button>
            </li>
          </ul>
        </div>
      </label>

      <label>
        Amount
        <input
          type="number"
          :value="props.pairConfig.amount"
          aria-label="Amount"
          @input="updateNumber('amount', $event)"
        />
      </label>

      <label>
        Limit factor
        <input
          type="number"
          step="0.01"
          :value="props.pairConfig.limit_factor"
          aria-label="Limit factor"
          @input="updateNumber('limit_factor', $event)"
        />
      </label>

      <label>
        Max price
        <input
          type="number"
          :value="props.pairConfig.max_price"
          aria-label="Max price"
          @input="updateNumber('max_price', $event)"
        />
      </label>

      <label class="checkbox">
        <input
          type="checkbox"
          :checked="props.pairConfig.ignore_differing_orders ?? false"
          aria-label="Ignore differing orders"
          @change="updateBoolean('ignore_differing_orders', $event)"
        />
        Ignore differing orders
      </label>
    </div>

    <ul v-if="Object.keys(props.fieldErrors).length > 0" class="errors">
      <li v-for="[field, message] in Object.entries(props.fieldErrors)" :key="field">
        {{ message }}
      </li>
    </ul>

    <ScheduleEditor
      :schedule="props.pairConfig.schedule ?? {}"
      :min-order-interval-minutes="props.pairConfig.min_order_interval_minutes ?? 30"
      :field-errors="scheduleFieldErrors"
      @update:schedule="updateSchedule"
      @update:min-order-interval-minutes="updateMinInterval"
    />

    <article v-if="props.manualRunState" class="manual-run">
      <strong>{{ props.manualRunState.status }}</strong>
      <span>{{ props.manualRunState.message }}</span>
      <span v-if="props.manualRunState.orderTxid">{{ props.manualRunState.orderTxid }}</span>
    </article>
  </article>
</template>

<style scoped>
.pair-editor {
  display: grid;
  gap: var(--space-md);
  padding: var(--space-md);
  border: var(--rule-hairline);
  border-radius: var(--radius-lg);
  background: var(--color-paper-3);
}

header,
.actions,
.manual-run {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

header {
  justify-content: space-between;
}

.eyebrow {
  margin: 0 0 var(--space-2xs);
  color: var(--color-accent);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--text-lg);
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr));
  gap: var(--space-sm);
}

label {
  display: grid;
  gap: var(--space-2xs);
  color: var(--color-ink-2);
  font-weight: 700;
}

.pair-combobox {
  position: relative;
}

.pair-combobox-control {
  position: relative;
}

.pair-combobox-control input {
  width: 100%;
}

.pair-suggestions {
  position: absolute;
  z-index: var(--z-dropdown);
  top: calc(100% + var(--space-2xs));
  left: 0;
  right: 0;
  display: grid;
  max-height: 14rem;
  margin: 0;
  padding: var(--space-2xs);
  overflow-y: auto;
  list-style: none;
  border: var(--rule-strong);
  border-radius: var(--radius-sm);
  background: var(--color-paper);
}

.pair-suggestions button {
  display: grid;
  width: 100%;
  gap: var(--space-3xs);
  padding: var(--space-xs) var(--space-sm);
  border: 0;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--color-ink);
  text-align: left;
  cursor: pointer;
}

.pair-suggestions button:hover,
.pair-suggestions button:focus-visible {
  background: var(--color-accent-soft);
  color: var(--color-ink);
  outline: none;
}

.pair-suggestions small,
.pair-suggestion-status {
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.pair-suggestion-status {
  padding: var(--space-xs) var(--space-sm);
}

.checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.checkbox input {
  width: auto;
  min-height: auto;
  accent-color: var(--color-accent);
}

.errors {
  margin: 0;
  padding: var(--space-sm) var(--space-sm) var(--space-sm) var(--space-lg);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-sm);
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.manual-run {
  justify-content: flex-start;
  padding: var(--space-sm);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-sm);
  background: var(--color-success-soft);
  color: var(--color-ink);
}

.manual-run span {
  color: var(--color-ink-2);
}

@media (max-width: 42rem) {
  header,
  .actions,
  .manual-run {
    display: grid;
  }
}
</style>
