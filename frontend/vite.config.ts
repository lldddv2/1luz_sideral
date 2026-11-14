import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // MapLibre 6 loads its worker via a URL relative to its own module;
  // Vite's dependency pre-bundling breaks that path, so serve it as-is.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
})
