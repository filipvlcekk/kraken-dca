import { defineConfig } from "deepsec/config";

export default defineConfig({
  projects: [
    { id: "web-ui-cron-scheduler", root: ".." },
    // <deepsec:projects-insert-above>
  ],
});
