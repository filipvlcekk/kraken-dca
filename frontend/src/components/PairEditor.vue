<script setup lang="ts">
import { computed } from 'vue'

import type { DcaPairConfig, DcaPairSchedule } from '../api'
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

function updateString(field: 'pair', event: Event): void {
  updatePair({ [field]: (event.target as HTMLInputElement).value })
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
      <label>
        Pair name
        <input
          :value="props.pairConfig.pair"
          aria-label="Pair name"
          autocomplete="off"
          @input="updateString('pair', $event)"
        />
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
  gap: 1rem;
  padding: 1.1rem;
  border: 1px solid rgba(34, 50, 35, 0.13);
  border-radius: 26px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.76), rgba(239, 233, 213, 0.7)),
    radial-gradient(circle at bottom left, rgba(83, 118, 73, 0.15), transparent 36%);
}

header,
.actions,
.manual-run {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

header {
  justify-content: space-between;
}

.eyebrow {
  margin: 0 0 0.2rem;
  color: #69705a;
  font-size: 0.75rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h2 {
  margin: 0;
}

.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem;
}

label {
  display: grid;
  gap: 0.3rem;
}

.checkbox {
  display: flex;
  align-items: center;
}

.errors {
  margin: 0;
  padding-left: 1.2rem;
  color: #7c391c;
}

.manual-run {
  justify-content: flex-start;
  padding: 0.75rem;
  border-radius: 16px;
  background: rgba(68, 101, 58, 0.1);
}
</style>
