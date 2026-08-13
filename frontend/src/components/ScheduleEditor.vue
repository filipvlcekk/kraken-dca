<script setup lang="ts">
import { computed, ref } from 'vue'

import type { DcaPairSchedule } from '../api'
import {
  buildEveryMinutesCron,
  cronRunsMoreFrequentlyThan,
  describeCron,
  previewNextRuns,
  validateCron,
} from '../schedule'

const props = defineProps<{
  schedule: DcaPairSchedule
  minOrderIntervalMinutes: number
  fieldErrors: Record<string, string>
}>()

const emit = defineEmits<{
  'update:schedule': [schedule: DcaPairSchedule]
  'update:minOrderIntervalMinutes': [value: number]
}>()

const advancedMode = ref(false)
const timezones = ['UTC', 'Europe/Prague'] as const
const presets = [
  { value: 'daily-9', label: 'Daily at 09:00', cron: '0 9 * * *' },
  { value: 'every-15-minutes', label: 'Every 15 minutes', cron: buildEveryMinutesCron(15) },
  { value: 'every-30-minutes', label: 'Every 30 minutes', cron: buildEveryMinutesCron(30) },
] as const

const enabled = computed(() => props.schedule.enabled ?? true)
const cron = computed(() => props.schedule.cron ?? '0 9 * * *')
const timezone = computed(() => props.schedule.timezone ?? 'UTC')
const selectedPreset = computed(() => {
  return presets.find((preset) => preset.cron === cron.value)?.value ?? 'advanced'
})
const validationError = computed(() => validateCron(cron.value))
const summaryText = computed(() => {
  if (!enabled.value) {
    return 'Scheduled DCA disabled'
  }
  if (validationError.value !== null) {
    return validationError.value
  }
  if (cron.value === '0 9 * * *') {
    return 'Every day at 09:00 AM'
  }
  return describeCron(cron.value)
})
const nextRuns = computed(() => {
  if (!enabled.value || validationError.value !== null) {
    return []
  }
  try {
    return previewNextRuns(cron.value, timezone.value, 3)
  } catch {
    return []
  }
})
const intervalWarning = computed(() => {
  if (!enabled.value || validationError.value !== null) {
    return null
  }
  if (!cronRunsMoreFrequentlyThan(cron.value, timezone.value, props.minOrderIntervalMinutes)) {
    return null
  }
  return `Runs more often than the ${props.minOrderIntervalMinutes} minute safety interval.`
})

function emitSchedule(patch: Partial<DcaPairSchedule>): void {
  emit('update:schedule', {
    enabled: enabled.value,
    cron: cron.value,
    timezone: timezone.value,
    ...patch,
  })
}

function onPresetChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  const preset = presets.find((candidate) => candidate.value === value)
  if (preset === undefined) {
    advancedMode.value = true
    return
  }
  advancedMode.value = false
  emitSchedule({ cron: preset.cron })
}

function onCronInput(event: Event): void {
  emitSchedule({ cron: (event.target as HTMLInputElement).value })
}

function onTimezoneChange(event: Event): void {
  emitSchedule({ timezone: (event.target as HTMLSelectElement).value })
}

function onEnabledChange(event: Event): void {
  emitSchedule({ enabled: (event.target as HTMLInputElement).checked })
}

function onMinIntervalInput(event: Event): void {
  emit('update:minOrderIntervalMinutes', Number((event.target as HTMLInputElement).value))
}
</script>

<template>
  <section class="schedule-editor">
    <label class="toggle">
      <input
        type="checkbox"
        aria-label="Enable scheduled DCA"
        :checked="enabled"
        @change="onEnabledChange"
      />
      Scheduled DCA
    </label>

    <label>
      Preset
      <select
        aria-label="Schedule preset"
        :value="selectedPreset"
        @change="onPresetChange"
      >
        <option v-for="preset in presets" :key="preset.value" :value="preset.value">
          {{ preset.label }}
        </option>
        <option value="advanced">Advanced cron</option>
      </select>
    </label>

    <button type="button" aria-label="Use advanced cron" @click="advancedMode = true">
      Use advanced cron
    </button>

    <label v-if="advancedMode || selectedPreset === 'advanced'">
      Cron expression
      <input
        :value="cron"
        aria-label="Cron expression"
        autocomplete="off"
        @input="onCronInput"
      />
    </label>

    <label>
      Timezone
      <select aria-label="Timezone" :value="timezone" @change="onTimezoneChange">
        <option v-for="zone in timezones" :key="zone" :value="zone">
          {{ zone }}
        </option>
      </select>
    </label>

    <label>
      Minimum order interval
      <input
        type="number"
        min="0"
        :value="props.minOrderIntervalMinutes"
        aria-label="Minimum order interval minutes"
        @input="onMinIntervalInput"
      />
    </label>

    <article class="summary">
      <strong>{{ summaryText }}</strong>
      <span>{{ timezone }}</span>
    </article>

    <ul v-if="nextRuns.length > 0" class="next-runs">
      <li v-for="run in nextRuns" :key="run">{{ run }}</li>
    </ul>

    <p v-if="intervalWarning" class="warning">{{ intervalWarning }}</p>

    <ul v-if="Object.keys(props.fieldErrors).length > 0" class="errors">
      <li v-for="[field, message] in Object.entries(props.fieldErrors)" :key="field">
        {{ message }}
      </li>
    </ul>
  </section>
</template>

<style scoped>
.schedule-editor {
  display: grid;
  gap: var(--space-sm);
  padding-block-start: var(--space-md);
  border-block-start: var(--rule-hairline);
}

.schedule-editor label {
  display: grid;
  gap: var(--space-2xs);
  color: var(--color-ink-2);
  font-size: var(--text-base);
  font-weight: 700;
}

.toggle {
  display: flex;
  align-items: center;
  grid-template-columns: auto 1fr;
  gap: var(--space-xs);
}

.toggle input {
  width: auto;
  min-height: auto;
  accent-color: var(--color-accent);
}

.summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  align-items: center;
  padding: var(--space-sm);
  border: var(--rule-hairline);
  border-radius: var(--radius-sm);
  background: var(--color-paper-3);
  color: var(--color-ink);
}

.summary span {
  color: var(--color-muted);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.next-runs,
.errors {
  margin: 0;
  padding-left: var(--space-lg);
  color: var(--color-muted);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.warning,
.errors {
  color: var(--color-warning);
}

.warning {
  margin: 0;
  padding: var(--space-sm);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-sm);
  background: var(--color-warning-soft);
}
</style>
