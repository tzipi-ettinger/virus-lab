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
})
