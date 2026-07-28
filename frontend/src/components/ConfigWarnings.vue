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
  gap: 0.75rem;
}

.warning {
  padding: 1rem;
  border: 1px solid rgba(160, 74, 38, 0.24);
  border-radius: 18px;
  background: rgba(255, 237, 207, 0.8);
  color: #532f15;
}

.warning h2,
.warning p {
  margin: 0;
}

.warning ul {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
}
</style>
