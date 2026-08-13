<script setup lang="ts">
defineProps<{
  configValid: boolean
  validationErrors: Record<string, string>
  configPersistenceError?: string | null
  orderHistoryWarning?: string | null
  setupMode: boolean
}>()
</script>

<template>
  <section
    v-if="
      setupMode ||
      !configValid ||
      configPersistenceError ||
      orderHistoryWarning
    "
    class="warnings"
  >
    <article v-if="setupMode" class="warning">
      <h2>Setup mode</h2>
      <p>Create and save a valid config.yaml to start the scheduler.</p>
    </article>

    <article v-else-if="!configValid" class="warning">
      <h2>Degraded config mode</h2>
      <p>Fix the saved configuration before scheduler changes can be applied.</p>
    </article>

    <article v-if="Object.keys(validationErrors).length > 0" class="warning">
      <h2>Validation errors</h2>
      <ul>
        <li
          v-for="[field, message] in Object.entries(validationErrors)"
          :key="field"
        >
          <strong>{{ field }}</strong>: {{ message }}
        </li>
      </ul>
    </article>

    <article v-if="configPersistenceError" class="warning">
      <h2>Config persistence failed</h2>
      <p>{{ configPersistenceError }}</p>
    </article>

    <article v-if="orderHistoryWarning" class="warning">
      <h2>Order history warning</h2>
      <p>{{ orderHistoryWarning }}</p>
    </article>
  </section>
</template>

<style scoped>
.warnings {
  display: grid;
  gap: var(--space-sm);
}

.warning {
  padding: var(--space-md);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-md);
  background: var(--color-warning-soft);
  color: var(--color-ink);
}

.warning h2,
.warning p {
  margin: 0;
}

.warning h2 {
  font-family: var(--font-display);
  font-size: var(--text-md);
}

.warning p,
.warning li {
  color: var(--color-ink-2);
}

.warning ul {
  margin: var(--space-xs) 0 0;
  padding-left: var(--space-lg);
}
</style>
