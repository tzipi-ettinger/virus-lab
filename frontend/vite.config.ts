/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev: the browser calls /api on the Vite origin and Vite forwards it to
    // FastAPI, so local dev does not depend on CORS.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    // 5s (the default) times out on a loaded machine, and under coverage.
    testTimeout: 15_000,
    // `npm run test:coverage` (CI). The thresholds are a floor a bit under today's
    // numbers: a PR that drops below fails, so raise them as coverage grows.
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      exclude: ['src/**/*.test.*', 'src/api/schema.d.ts', 'src/main.tsx', 'src/vite-env.d.ts'],
      reporter: ['text-summary', 'text'],
      // 22.10: statements 94.9%, branches 87.3%, functions 93.3%, lines 96.2%.
      thresholds: { statements: 93, branches: 85, functions: 91, lines: 94 },
    },
  },
})
