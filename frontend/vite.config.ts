import { defineConfig } from 'vite'
import type { InlineConfig } from 'vitest/node'
import vue from '@vitejs/plugin-vue'

declare module 'vite' {
  interface UserConfig {
    test?: InlineConfig
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    passWithNoTests: true,
  },
})
