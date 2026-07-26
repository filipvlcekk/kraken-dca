<template>
  <main class="shell">
    <div class="eyebrow">Docker Web UI</div>
    <h1>Kraken DCA scheduler</h1>
    <p>
      Frontend scaffold is ready for authenticated config editing, per-pair cron
      schedules, and manual run controls.
    </p>
  </main>
</template>

<style scoped>
.shell {
  max-width: 760px;
  padding: 4rem;
  border: 1px solid rgba(45, 44, 35, 0.12);
  border-radius: 32px;
  background: rgba(255, 248, 232, 0.82);
  box-shadow: 0 30px 90px rgba(42, 50, 32, 0.16);
}

.eyebrow {
  margin-bottom: 1rem;
  color: #7c4b1d;
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: #202519;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(2.6rem, 8vw, 6.5rem);
  line-height: 0.9;
  letter-spacing: -0.07em;
}

p {
  max-width: 560px;
  margin: 1.5rem 0 0;
  color: #4d563c;
  font-size: clamp(1rem, 2vw, 1.3rem);
}
</style>
