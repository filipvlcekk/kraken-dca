<script setup lang="ts">
import { computed } from 'vue'

import type { HistoryChartPoint } from '../api'

const props = defineProps<{
  points: HistoryChartPoint[]
  estimatedValue: string | null
}>()

const width = 640
const height = 220
const padding = 28

const values = computed(() => {
  const spent = props.points.map((point) => Number(point.cumulative_spent))
  const estimate = props.estimatedValue === null ? [] : [Number(props.estimatedValue)]
  return [...spent, ...estimate].filter((value) => Number.isFinite(value))
})

const path = computed(() => {
  if (props.points.length === 0 || values.value.length === 0) {
    return ''
  }
  const max = Math.max(...values.value, 1)
  return props.points.map((point, index) => {
    const x = scaleX(index)
    const y = scaleY(Number(point.cumulative_spent), max)
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
  }).join(' ')
})

const estimateY = computed(() => {
  if (props.estimatedValue === null || values.value.length === 0) {
    return null
  }
  return scaleY(Number(props.estimatedValue), Math.max(...values.value, 1))
})

function scaleX(index: number): number {
  if (props.points.length <= 1) {
    return width / 2
  }
  return padding + (index / (props.points.length - 1)) * (width - padding * 2)
}

function scaleY(value: number, max: number): number {
  return height - padding - (value / max) * (height - padding * 2)
}
</script>

<template>
  <section class="chart-panel" aria-label="P/L chart">
    <div class="panel-heading">
      <p class="eyebrow">P/L chart</p>
      <h2>Buying history and estimate</h2>
    </div>

    <p v-if="points.length === 0" class="empty-state">
      No completed orders yet.
    </p>

    <div v-else class="chart-wrap">
      <svg role="img" :viewBox="`0 0 ${width} ${height}`" preserveAspectRatio="none">
        <title>Buying history and current estimated value</title>
        <line
          x1="28"
          :y1="height - padding"
          :x2="width - padding"
          :y2="height - padding"
          class="axis"
        />
        <path :d="path" class="spent-line" />
        <line
          v-if="estimateY !== null"
          :x1="padding"
          :x2="width - padding"
          :y1="estimateY"
          :y2="estimateY"
          class="estimate-line"
        />
      </svg>
      <div class="legend">
        <span><i class="spent-key"></i>Money spent</span>
        <span><i class="estimate-key"></i>Worth now</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.chart-panel {
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

.chart-wrap {
  display: grid;
  gap: var(--space-sm);
}

svg {
  width: 100%;
  height: 240px;
  border: var(--rule-hairline);
  border-radius: var(--radius-sm);
  background: var(--color-paper-1);
}

.axis {
  stroke: var(--color-border);
  stroke-width: 1;
}

.spent-line {
  fill: none;
  stroke: var(--color-accent);
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3;
}

.estimate-line {
  stroke: var(--color-success);
  stroke-dasharray: 8 6;
  stroke-width: 2;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  color: var(--color-muted);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.legend span {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2xs);
}

i {
  width: 1rem;
  height: 0.18rem;
  border-radius: var(--radius-xs);
}

.spent-key {
  background: var(--color-accent);
}

.estimate-key {
  background: var(--color-success);
}
</style>
